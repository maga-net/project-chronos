#!/usr/bin/env python
# -*- coding: utf-8 -*-

# project-chronos/oracle_simulation.py

"""
Project Chronos: A Cross-Chain Bridge Oracle Simulation

This script simulates the core off-chain component (an oracle or relayer) of a 
cross-chain asset bridge. It listens for 'TokensLocked' events on a source 
blockchain, validates them, and simulates the process of minting corresponding 
'wrapped' tokens on a destination blockchain.

Author: Senior Blockchain Architect
Version: 1.0.0
"""

import os
import time
import json
import logging
from typing import Dict, Any, List, Optional

import requests
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import BlockNotFound
from dotenv import load_dotenv

# --- Configuration & Setup ---

load_dotenv()

# Basic logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- Constants and Placeholders ---

# These would be the actual ABIs of your smart contracts.
# For this simulation, we're using a minimal ABI for the event we care about.
SOURCE_CHAIN_BRIDGE_ABI = json.dumps([
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "sender", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "token", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "destinationChainId", "type": "uint256"},
            {"indexed": False, "internalType": "bytes32", "name": "transactionId", "type": "bytes32"}
        ],
        "name": "TokensLocked",
        "type": "event"
    }
])

DESTINATION_CHAIN_MINT_ABI = json.dumps([
    {
        "inputs": [
            {"internalType": "address", "name": "recipient", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "bytes32", "name": "sourceTransactionId", "type": "bytes32"}
        ],
        "name": "mintWrappedTokens",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
])

STATE_FILE = 'oracle_state.json'

# --- Classes ---

class BlockchainConnector:
    """Handles the connection to a blockchain node via Web3.py."""

    def __init__(self, rpc_url: str, chain_name: str):
        """
        Initializes the connector.
        Args:
            rpc_url (str): The HTTP RPC provider URL for the blockchain node.
            chain_name (str): A human-readable name for the chain (for logging).
        """
        self.logger = logging.getLogger(f"BlockchainConnector[{chain_name}]")
        self.chain_name = chain_name
        try:
            self.w3 = Web3(Web3.HTTPProvider(rpc_url))
            if not self.w3.is_connected():
                raise ConnectionError(f"Failed to connect to {self.chain_name} RPC.")
            self.logger.info(f"Successfully connected to {self.chain_name}. Chain ID: {self.w3.eth.chain_id}")
        except Exception as e:
            self.logger.error(f"Error initializing connection to {self.chain_name}: {e}")
            raise

    def get_contract(self, address: str, abi: str) -> Optional[Contract]:
        """
        Returns a Web3 contract instance.
        Args:
            address (str): The contract's address.
            abi (str): The contract's ABI.
        Returns:
            Optional[Contract]: A Web3 contract instance, or None on error.
        """
        try:
            checksum_address = Web3.to_checksum_address(address)
            return self.w3.eth.contract(address=checksum_address, abi=abi)
        except ValueError as e:
            self.logger.error(f"Invalid address or ABI for {self.chain_name}: {e}")
            return None

class BridgeContractEventHandler:
    """Listens for specific events from the bridge contract on the source chain."""

    def __init__(self, connector: BlockchainConnector, contract_address: str, contract_abi: str):
        """
        Initializes the event handler.
        Args:
            connector (BlockchainConnector): The connector for the source chain.
            contract_address (str): The address of the bridge contract.
            contract_abi (str): The ABI of the bridge contract.
        """
        self.logger = logging.getLogger(f"EventHandler[{connector.chain_name}]")
        self.connector = connector
        self.contract = connector.get_contract(contract_address, contract_abi)
        if not self.contract:
            raise ValueError("Failed to instantiate contract for event handler.")

    def get_events(self, from_block: int, to_block: int) -> List[Dict[str, Any]]:
        """
        Fetches 'TokensLocked' events within a given block range.
        Args:
            from_block (int): The starting block number.
            to_block (int): The ending block number.
        Returns:
            List[Dict[str, Any]]: A list of decoded event logs.
        """
        try:
            event_filter = self.contract.events.TokensLocked.create_filter(
                fromBlock=from_block,
                toBlock=to_block
            )
            events = event_filter.get_all_entries()
            if events:
                self.logger.info(f"Found {len(events)} 'TokensLocked' event(s) between blocks {from_block}-{to_block}.")
            return [dict(event) for event in events]
        except BlockNotFound:
            self.logger.warning(f"Block range {from_block}-{to_block} not found. The chain might not be synced that far.")
            return []
        except Exception as e:
            self.logger.error(f"An unexpected error occurred while fetching events: {e}")
            return []

class TransactionValidator:
    """Performs validation on the event data before processing."""

    # A simple in-memory cache to prevent processing the same transaction twice (replay attack).
    # In a real system, this would be a persistent database (e.g., Redis, PostgreSQL).
    _processed_tx_ids = set()

    def __init__(self, supported_tokens: Dict[str, float], min_lock_amount: float):
        """
        Initializes the validator.
        Args:
            supported_tokens (Dict[str, float]): A dictionary mapping supported token addresses to their max allowed value in USD.
            min_lock_amount (float): The minimum lock amount in USD to be considered valid.
        """
        self.logger = logging.getLogger("TransactionValidator")
        self.supported_tokens = {Web3.to_checksum_address(k): v for k, v in supported_tokens.items()}
        self.min_lock_amount = min_lock_amount
        self.api_url = "https://api.coingecko.com/api/v3/simple/price"

    def _get_token_price_usd(self, token_symbol: str) -> Optional[float]:
        """ 
        Fetches token price from an external API (CoinGecko). This is a dependency.
        In a real-world scenario, you might use multiple oracles (e.g., Chainlink).
        """
        try:
            # A simple mapping for simulation purposes. A real system would need a more robust registry.
            symbol_to_id = {
                'WETH': 'ethereum',
                'USDC': 'usd-coin'
            }
            params = {'ids': symbol_to_id.get(token_symbol, ''), 'vs_currencies': 'usd'}
            response = requests.get(self.api_url, params=params)
            response.raise_for_status()
            data = response.json()
            return data[symbol_to_id[token_symbol]]['usd']
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to fetch price for {token_symbol} from CoinGecko: {e}")
            return None
        except (KeyError, IndexError):
            self.logger.warning(f"Price not found for symbol {token_symbol}.")
            return None

    def validate(self, event_data: Dict[str, Any]) -> bool:
        """
        Runs a series of checks on the event data.
        Args:
            event_data (Dict[str, Any]): The decoded event log.
        Returns:
            bool: True if the event is valid, False otherwise.
        """
        tx_id = event_data['args']['transactionId'].hex()
        token_address = event_data['args']['token']
        amount_wei = event_data['args']['amount']
        amount_ether = Web3.from_wei(amount_wei, 'ether') # Assuming 18 decimals for simplicity

        self.logger.info(f"Validating transaction ID: {tx_id}")

        # 1. Check for replay attacks
        if tx_id in self._processed_tx_ids:
            self.logger.warning(f"Replay attack detected! Transaction {tx_id} already processed.")
            return False

        # 2. Check if the token is supported
        if token_address not in self.supported_tokens:
            self.logger.warning(f"Unsupported token: {token_address} for transaction {tx_id}.")
            return False

        # 3. Check value against limits (using external price oracle)
        # This is a placeholder. A real implementation needs a token address to symbol mapping.
        token_symbol = 'WETH' if 'c02' in token_address else 'USDC' # Mock logic
        price_usd = self._get_token_price_usd(token_symbol)
        if price_usd is None:
            self.logger.error(f"Could not retrieve price for validation of transaction {tx_id}. Skipping.")
            return False

        value_usd = float(amount_ether) * price_usd
        self.logger.info(f"Transaction {tx_id} details: {amount_ether} {token_symbol} (~${value_usd:.2f})")

        if value_usd < self.min_lock_amount:
            self.logger.warning(f"Transaction {tx_id} value ${value_usd:.2f} is below minimum of ${self.min_lock_amount}.")
            return False

        max_value = self.supported_tokens[token_address]
        if value_usd > max_value:
            self.logger.warning(f"Transaction {tx_id} value ${value_usd:.2f} is above maximum of ${max_value}.")
            return False

        self.logger.info(f"Transaction {tx_id} passed all validation checks.")
        self._processed_tx_ids.add(tx_id)
        return True


class DestinationChainMinter:
    """Simulates the minting of tokens on the destination chain."""

    def __init__(self, connector: BlockchainConnector, contract_address: str, contract_abi: str, oracle_pk: str):
        """
        Initializes the minter.
        Args:
            connector (BlockchainConnector): The connector for the destination chain.
            contract_address (str): Address of the destination chain contract.
            contract_abi (str): ABI of the destination chain contract.
            oracle_pk (str): Private key of the oracle account for signing transactions.
        """ 
        self.logger = logging.getLogger(f"Minter[{connector.chain_name}]")
        self.connector = connector
        self.contract = connector.get_contract(contract_address, contract_abi)
        self.oracle_account = self.connector.w3.eth.account.from_key(oracle_pk)
        self.logger.info(f"Minter initialized for account: {self.oracle_account.address}")

        if not self.contract:
            raise ValueError("Failed to instantiate contract for minter.")

    def submit_mint_transaction(self, event_data: Dict[str, Any]):
        """
        Builds and simulates sending a transaction to mint wrapped tokens.
        Args:
            event_data (Dict[str, Any]): The validated event log from the source chain.
        """
        args = event_data['args']
        recipient = args['sender']
        amount = args['amount']
        source_tx_id = args['transactionId']

        self.logger.info(f"Preparing to mint {Web3.from_wei(amount, 'ether')} tokens for {recipient} on {self.connector.chain_name}.")

        try:
            # --- This is the core simulation part ---
            # In a real system, you would build, sign, and send the transaction.
            
            # 1. Build the transaction
            nonce = self.connector.w3.eth.get_transaction_count(self.oracle_account.address)
            tx_payload = {
                'from': self.oracle_account.address,
                'nonce': nonce,
                'gas': 200000, # Estimated gas
                'gasPrice': self.connector.w3.eth.gas_price
            }
            
            unsigned_tx = self.contract.functions.mintWrappedTokens(
                recipient,
                amount,
                source_tx_id
            ).build_transaction(tx_payload)

            # 2. Sign the transaction
            signed_tx = self.connector.w3.eth.account.sign_transaction(unsigned_tx, private_key=self.oracle_account.key)

            # 3. Send the transaction (SIMULATED)
            # tx_hash = self.connector.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            # self.logger.info(f"Transaction sent! Hash: {tx_hash.hex()}")
            # receipt = self.connector.w3.eth.wait_for_transaction_receipt(tx_hash)
            # self.logger.info(f"Transaction confirmed in block: {receipt.blockNumber}")

            self.logger.info(f"[SIMULATION] Transaction to mint tokens would be sent now.")
            self.logger.info(f"[SIMULATION]   - To: {self.contract.address}")
            self.logger.info(f"[SIMULATION]   - Function: mintWrappedTokens(recipient={recipient}, amount={amount}, sourceTransactionId={source_tx_id.hex()})")
            self.logger.info(f"[SIMULATION]   - Signed TX Hash (raw): {signed_tx.hash.hex()}")

        except Exception as e:
            self.logger.error(f"Failed to build or sign minting transaction: {e}")


class BridgeOracle:
    """The main orchestrator for the bridge oracle simulation."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initializes the entire oracle service from a configuration dictionary.
        """
        self.logger = logging.getLogger("BridgeOracle")
        self.config = config
        self.state = self._load_state()

        # --- Setup components ---
        self.source_connector = BlockchainConnector(
            rpc_url=config['source_chain']['rpc_url'],
            chain_name=config['source_chain']['name']
        )
        self.dest_connector = BlockchainConnector(
            rpc_url=config['destination_chain']['rpc_url'],
            chain_name=config['destination_chain']['name']
        )
        self.event_handler = BridgeContractEventHandler(
            connector=self.source_connector,
            contract_address=config['source_chain']['bridge_contract'],
            contract_abi=SOURCE_CHAIN_BRIDGE_ABI
        )
        self.validator = TransactionValidator(
            supported_tokens=config['validator']['supported_tokens'],
            min_lock_amount=config['validator']['min_lock_amount_usd']
        )
        self.minter = DestinationChainMinter(
            connector=self.dest_connector,
            contract_address=config['destination_chain']['mint_contract'],
            contract_abi=DESTINATION_CHAIN_MINT_ABI,
            oracle_pk=config['oracle']['private_key']
        )
        self.poll_interval = config['oracle']['poll_interval_seconds']
        self.block_chunk_size = config['oracle']['block_chunk_size']

    def _load_state(self) -> Dict[str, Any]:
        """Loads the last processed block number from a file."""
        try:
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                self.logger.info(f"Loaded state from {STATE_FILE}: {state}")
                return state
        except (FileNotFoundError, json.JSONDecodeError):
            self.logger.warning(f"State file not found or invalid. Starting from configured block.")
            return {'last_processed_block': self.config['source_chain']['start_block']}

    def _save_state(self):
        """Saves the current state (last processed block) to a file."""
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.state, f)
                self.logger.debug(f"Saved state to {STATE_FILE}")
        except IOError as e:
            self.logger.error(f"Failed to save state to {STATE_FILE}: {e}")

    def run(self):
        """Starts the main event loop for the oracle."""
        self.logger.info("--- Project Chronos Oracle starting up ---")
        while True:
            try:
                # Determine block range to scan
                latest_block = self.source_connector.w3.eth.block_number
                from_block = self.state['last_processed_block'] + 1
                
                # To avoid requesting a huge range, process in chunks
                to_block = min(latest_block, from_block + self.block_chunk_size - 1)

                if from_block > to_block:
                    self.logger.info(f"No new blocks to process. Current head: {latest_block}. Waiting...")
                    time.sleep(self.poll_interval)
                    continue

                self.logger.info(f"Scanning for events from block {from_block} to {to_block}...")
                
                # Fetch and process events
                events = self.event_handler.get_events(from_block, to_block)
                for event in events:
                    self.logger.info(f"Processing event from transaction: {event['transactionHash'].hex()}")
                    if self.validator.validate(event):
                        self.minter.submit_mint_transaction(event)
                    else:
                        self.logger.warning(f"Validation failed for event in tx {event['transactionHash'].hex()}. Skipping.")

                # Update and save state
                self.state['last_processed_block'] = to_block
                self._save_state()

                # Wait before the next poll if we are caught up
                if to_block >= latest_block - 1:
                    time.sleep(self.poll_interval)

            except KeyboardInterrupt:
                self.logger.info("--- Shutting down oracle ---")
                break
            except Exception as e:
                self.logger.critical(f"A critical error occurred in the main loop: {e}")
                self.logger.info(f"Restarting loop after {self.poll_interval * 2} seconds...")
                time.sleep(self.poll_interval * 2)


def main():
    """Main entry point of the script."""
    # --- Configuration ---
    # In a real application, this would come from a more robust config system
    # (e.g., YAML file, environment variables).
    config = {
        'source_chain': {
            'name': 'Ethereum-Sepolia',
            'rpc_url': os.getenv('SOURCE_CHAIN_RPC_URL'),
            'bridge_contract': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D', # Placeholder: Uniswap Router
            'start_block': 19000000 # A recent block number for a testnet like Sepolia
        },
        'destination_chain': {
            'name': 'Polygon-Mumbai',
            'rpc_url': os.getenv('DESTINATION_CHAIN_RPC_URL'),
            'mint_contract': '0x000000000000000000000000000000000000dead' # Placeholder
        },
        'oracle': {
            'private_key': os.getenv('ORACLE_PRIVATE_KEY'),
            'poll_interval_seconds': 15,
            'block_chunk_size': 100
        },
        'validator': {
            'supported_tokens': {
                '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2': 50000.0, # WETH, max $50k
                '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48': 100000.0 # USDC, max $100k
            },
            'min_lock_amount_usd': 10.0
        }
    }

    # Basic validation for required environment variables
    if not all([config['source_chain']['rpc_url'], config['destination_chain']['rpc_url'], config['oracle']['private_key']]):
        logging.error("Missing required environment variables. Please check your .env file.")
        logging.error("Required: SOURCE_CHAIN_RPC_URL, DESTINATION_CHAIN_RPC_URL, ORACLE_PRIVATE_KEY")
        return

    oracle = BridgeOracle(config)
    oracle.run()

if __name__ == "__main__":
    main()


