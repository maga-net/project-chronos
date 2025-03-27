import os
import json
import time
import logging
from typing import Dict, Any, List, Optional

import requests
from web3 import Web3
from web3.contract import Contract
from web3.logs import DISCARD
from web3.exceptions import BlockNotFound
from dotenv import load_dotenv

# --- Configuration Loading ---
load_dotenv()

# --- Basic Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


class Config:
    """A centralized class to hold all configuration parameters."""
    # Source Chain (e.g., Ethereum)
    SOURCE_CHAIN_RPC_URL = os.getenv('SOURCE_CHAIN_RPC_URL')
    SOURCE_CHAIN_BRIDGE_CONTRACT_ADDRESS = os.getenv('SOURCE_CHAIN_BRIDGE_CONTRACT_ADDRESS')

    # Destination Chain (e.g., Polygon)
    DESTINATION_CHAIN_RPC_URL = os.getenv('DESTINATION_CHAIN_RPC_URL')
    DESTINATION_CHAIN_MINT_CONTROLLER_ADDRESS = os.getenv('DESTINATION_CHAIN_MINT_CONTROLLER_ADDRESS')
    # The private key of the account that has minting permissions on the destination chain
    SIGNER_PRIVATE_KEY = os.getenv('SIGNER_PRIVATE_KEY')

    # Listener Configuration
    # Number of blocks to wait before considering an event confirmed, protects against reorgs
    CONFIRMATION_BLOCKS = int(os.getenv('CONFIRMATION_BLOCKS', '12'))
    # Time in seconds to wait between polling for new blocks
    POLL_INTERVAL_SECONDS = int(os.getenv('POLL_INTERVAL_SECONDS', '15'))
    # File to persist the last processed block number
    STATE_FILE = 'bridge_listener_state.json'
    # Gas price API for fallback gas estimation (optional)
    GAS_STATION_API_URL = os.getenv('GAS_STATION_API_URL')


class BlockchainConnector:
    """Handles all direct interactions with a blockchain node via Web3.py."""

    def __init__(self, rpc_url: str):
        """Initializes a connection to a blockchain node.

        Args:
            rpc_url (str): The HTTP or WebSocket RPC URL of the blockchain node.
        """
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            logging.error(f"Failed to connect to blockchain node at {rpc_url}")
            raise ConnectionError(f"Unable to connect to {rpc_url}")
        logging.info(f"Successfully connected to node. Chain ID: {self.w3.eth.chain_id}")

    def get_latest_block_number(self) -> int:
        """Fetches the most recent block number from the connected node."""
        try:
            return self.w3.eth.block_number
        except Exception as e:
            logging.error(f"Error fetching latest block number: {e}")
            return 0

    def get_contract(self, address: str, abi: List[Dict[str, Any]]) -> Contract:
        """Creates a Web3.py contract instance.

        Args:
            address (str): The contract's address.
            abi (List[Dict[str, Any]]): The contract's Application Binary Interface (ABI).

        Returns:
            Contract: A Web3.py contract object.
        """
        checksum_address = Web3.to_checksum_address(address)
        return self.w3.eth.contract(address=checksum_address, abi=abi)


class TransactionProcessor:
    """Processes confirmed events and simulates minting on the destination chain."""

    def __init__(self, connector: BlockchainConnector, contract_address: str, signer_key: str):
        """Initializes the processor.

        Args:
            connector (BlockchainConnector): The connector for the destination chain.
            contract_address (str): The address of the mint controller contract.
            signer_key (str): The private key of the authorized minter.
        """
        self.connector = connector
        self.w3 = connector.w3
        self.signer = self.w3.eth.account.from_key(signer_key)
        # A simple in-memory cache to prevent processing the same transaction twice in a single run
        self.processed_transactions = set()
        # Dummy ABI for simulation purposes
        self.mint_controller_abi = [{"name": "mintBridgedTokens", "type": "function", "inputs": [
            {"type": "bytes32", "name": "sourceTxHash"},
            {"type": "address", "name": "recipient"},
            {"type": "uint256", "name": "amount"}
        ]}]
        self.contract = self.connector.get_contract(contract_address, self.mint_controller_abi)

    def process_deposit_event(self, event: Dict[str, Any]) -> bool:
        """Validates and processes a single deposit event.

        Args:
            event (Dict[str, Any]): The event data from the source chain.

        Returns:
            bool: True if the simulation was successful, False otherwise.
        """
        tx_hash = event['transactionHash'].hex()
        log_index = event['logIndex']
        unique_event_id = f"{tx_hash}-{log_index}"

        if unique_event_id in self.processed_transactions:
            logging.warning(f"Skipping already processed event in this session: {unique_event_id}")
            return True

        logging.info(f"Processing new deposit event: {unique_event_id}")
        
        # Extract data from event arguments
        recipient = event['args']['recipient']
        amount = event['args']['amount']
        source_tx_hash_bytes = event['transactionHash']

        logging.info(f"  -> Recipient: {recipient}, Amount: {amount}")

        # --- SIMULATION OF MINTING TRANSACTION ---
        # In a real system, this would build, sign, and send a real transaction.
        # Here, we simulate the steps for architectural clarity.
        try:
            logging.info("Simulating mint transaction on destination chain...")

            # 1. Build the transaction
            nonce = self.w3.eth.get_transaction_count(self.signer.address)
            tx_payload = {
                'from': self.signer.address,
                'nonce': nonce,
                'gas': 200000,  # A sensible default for this operation
                'gasPrice': self._get_gas_price()
            }
            
            unsigned_tx = self.contract.functions.mintBridgedTokens(
                source_tx_hash_bytes, recipient, amount
            ).build_transaction(tx_payload)

            # 2. Sign the transaction
            signed_tx = self.w3.eth.account.sign_transaction(unsigned_tx, self.signer.key)

            # 3. (SIMULATED) Send the transaction
            # In a real scenario: tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            # receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            simulated_tx_hash = Web3.keccak(signed_tx.rawTransaction).hex()
            logging.info(f"  -> [SIMULATED] Transaction sent. Hash: {simulated_tx_hash}")
            logging.info(f"  -> [SIMULATED] Waiting for confirmation...")
            time.sleep(2) # Simulate network delay
            logging.info(f"  -> [SUCCESS] Mint for event {unique_event_id} confirmed on destination chain.")

            self.processed_transactions.add(unique_event_id)
            return True

        except Exception as e:
            logging.error(f"Failed to simulate mint transaction for event {unique_event_id}: {e}")
            return False

    def _get_gas_price(self) -> int:
        """Estimates gas price, with a fallback to an external API."""
        try:
            # Primary method: use the node's estimate
            return self.w3.eth.gas_price
        except Exception as e:
            logging.warning(f"Could not get gas price from node ({e}). Trying external API.")
            if Config.GAS_STATION_API_URL:
                try:
                    response = requests.get(Config.GAS_STATION_API_URL)
                    response.raise_for_status()
                    # Assuming the API returns JSON like {'fast': 100} in Gwei
                    gas_gwei = response.json().get('fast') 
                    return self.w3.to_wei(gas_gwei, 'gwei')
                except requests.RequestException as req_e:
                    logging.error(f"Failed to fetch gas price from API: {req_e}")
            # Fallback to a hardcoded value if all else fails
            logging.warning("Falling back to a hardcoded gas price of 20 Gwei.")
            return self.w3.to_wei(20, 'gwei')


class BridgeEventListener:
    """The main service that listens for events and orchestrates processing."""

    def __init__(self, config: Config):
        """Initializes the listener service with all its dependencies."""
        self.config = config
        self.source_connector = BlockchainConnector(config.SOURCE_CHAIN_RPC_URL)
        self.destination_connector = BlockchainConnector(config.DESTINATION_CHAIN_RPC_URL)

        self.tx_processor = TransactionProcessor(
            self.destination_connector,
            config.DESTINATION_CHAIN_MINT_CONTROLLER_ADDRESS,
            config.SIGNER_PRIVATE_KEY
        )

        # Minimal ABI for the event we are interested in
        self.source_bridge_abi = [{"name": "DepositMade", "type": "event", "anonymous": False, "inputs": [
            {"indexed": True, "name": "recipient", "type": "address"},
            {"indexed": False, "name": "amount", "type": "uint256"}
        ]}]
        self.source_bridge_contract = self.source_connector.get_contract(
            config.SOURCE_CHAIN_BRIDGE_CONTRACT_ADDRESS, 
            self.source_bridge_abi
        )

        self.last_processed_block = self._load_state()

    def _load_state(self) -> int:
        """Loads the last processed block number from the state file."""
        try:
            with open(self.config.STATE_FILE, 'r') as f:
                state = json.load(f)
                block = int(state.get('last_processed_block', 0))
                logging.info(f"Loaded state: Last processed block is {block}.")
                return block
        except (FileNotFoundError, json.JSONDecodeError):
            logging.warning("State file not found or invalid. Will start from the latest block.")
            return 0

    def _save_state(self):
        """Saves the current processed block number to the state file."""
        with open(self.config.STATE_FILE, 'w') as f:
            json.dump({'last_processed_block': self.last_processed_block}, f)
        logging.debug(f"Saved state: last_processed_block = {self.last_processed_block}")

    def start(self):
        """Starts the main event listening loop."""
        logging.info("--- Cross-Chain Bridge Event Listener Started ---")
        logging.info(f"Watching for 'DepositMade' events on contract: {self.config.SOURCE_CHAIN_BRIDGE_CONTRACT_ADDRESS}")
        
        while True:
            try:
                latest_block = self.source_connector.get_latest_block_number()
                if latest_block == 0:
                    logging.warning("Could not fetch latest block. Retrying...")
                    time.sleep(self.config.POLL_INTERVAL_SECONDS)
                    continue

                # If this is the first run, start from the current block to avoid processing the whole chain history
                if self.last_processed_block == 0:
                    logging.info("First run detected. Setting start block to current confirmed block.")
                    self.last_processed_block = latest_block - self.config.CONFIRMATION_BLOCKS

                # Define the block range to scan
                start_block = self.last_processed_block + 1
                # Ensure we leave a gap for confirmations
                end_block = latest_block - self.config.CONFIRMATION_BLOCKS

                if start_block > end_block:
                    logging.info(f"No new confirmed blocks to process. Current head: {latest_block}. Waiting...")
                    time.sleep(self.config.POLL_INTERVAL_SECONDS)
                    continue

                logging.info(f"Scanning for events from block {start_block} to {end_block}...")

                # Fetch events in the specified range
                event_filter = self.source_bridge_contract.events.DepositMade.create_filter(
                    fromBlock=start_block, 
                    toBlock=end_block
                )
                events = event_filter.get_all_entries()

                if events:
                    logging.info(f"Found {len(events)} new 'DepositMade' event(s).")
                    for event in events:
                        self.tx_processor.process_deposit_event(event)
                else:
                    logging.info("No new events found in this range.")

                # Update state and save
                self.last_processed_block = end_block
                self._save_state()

                time.sleep(self.config.POLL_INTERVAL_SECONDS)

            except BlockNotFound as e:
                logging.error(f"A requested block was not found (possibly due to a reorg): {e}. Resetting and retrying.")
                # A simple recovery strategy: reset the last processed block to be a bit further behind
                self.last_processed_block -= self.config.CONFIRMATION_BLOCKS * 2 
                self._save_state()
                time.sleep(self.config.POLL_INTERVAL_SECONDS)

            except Exception as e:
                logging.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
                time.sleep(self.config.POLL_INTERVAL_SECONDS * 2) # Longer sleep on unexpected errors


def main():
    """Main entry point for the script."""
    # Perform initial configuration checks
    required_vars = [
        'SOURCE_CHAIN_RPC_URL', 'SOURCE_CHAIN_BRIDGE_CONTRACT_ADDRESS',
        'DESTINATION_CHAIN_RPC_URL', 'DESTINATION_CHAIN_MINT_CONTROLLER_ADDRESS',
        'SIGNER_PRIVATE_KEY'
    ]
    if any(not os.getenv(var) for var in required_vars):
        logging.error("One or more required environment variables are not set. Please check your .env file.")
        logging.error(f"Required: {', '.join(required_vars)}")
        return

    config = Config()
    listener = BridgeEventListener(config)
    listener.start()


if __name__ == "__main__":
    main()
