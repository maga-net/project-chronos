# Project Chronos: A Cross-Chain Bridge Event Listener Simulation

This repository contains a Python-based simulation of a critical backend component for a cross-chain asset bridge. It acts as a highly reliable event listener that monitors a 'source' blockchain for specific events (e.g., asset deposits) and triggers corresponding actions on a 'destination' blockchain (e.g., minting a wrapped asset).

The script is designed with production-grade architectural principles in mind, including state persistence, resilience to blockchain re-organizations (reorgs), and robust error handling.

## Concept

The core concept is to bridge assets between two blockchains (Chain A and Chain B). The process is as follows:

1.  A user deposits an asset (e.g., ETH or an ERC20 token) into a Bridge Contract on Chain A.
2.  This action emits a `DepositMade` event, which includes details like the recipient's address on Chain B and the amount deposited.
3.  The **Project Chronos** listener, running on a secure server, is constantly scanning Chain A for these `DepositMade` events.
4.  Upon detecting a new, confirmed event, the listener's an authorized account (a 'Signer') to call a Mint Controller contract on Chain B.
5.  This call on Chain B mints a corresponding amount of a wrapped/pegged asset (e.g., `wETH`) and sends it to the user's specified recipient address.

This script simulates steps 3, 4, and 5, providing a robust framework for event detection and transaction orchestration.

## Code Architecture

The system is designed with a clear separation of concerns, implemented across several Python classes:

-   **`Config`**: A static class that loads and holds all necessary configuration from environment variables (`.env` file). This includes RPC URLs, contract addresses, and private keys, keeping sensitive data out of the codebase.

-   **`BlockchainConnector`**: This class is the sole interface to the blockchain nodes. It encapsulates all `web3.py` logic for connecting to a node, creating contract instances, and fetching block information. It can be instantiated separately for the source and destination chains.

-   **`TransactionProcessor`**: This is the 'business logic' component. It takes a confirmed event from the source chain and performs the necessary actions on the destination chain. In this simulation, it builds, signs, and *simulates* the sending of a minting transaction. It includes logic for estimating gas prices and preventing duplicate processing.

-   **`BridgeEventListener`**: This is the main orchestrator and the heart of the application. It manages the primary loop, which involves:
    -   Determining the correct range of blocks to scan.
    -   Using the `BlockchainConnector` to query for new events.
    -   Passing any new, confirmed events to the `TransactionProcessor`.
    -   Managing state (i.e., the last block number processed) by saving it to a local JSON file (`bridge_listener_state.json`) to ensure continuity between restarts.

## How it Works

The listener operates in a continuous loop, following these steps:

1.  **Initialization**: On startup, the listener loads its configuration and reads the `bridge_listener_state.json` file to determine the last block it successfully processed. If the file doesn't exist, it prepares to start from the current block.

2.  **Fetch Latest Block**: It queries the source chain's RPC node to get the current latest block number.

3.  **Apply Confirmation Delay**: To protect against blockchain reorgs, it does not process events from the most recent blocks. It subtracts a `CONFIRMATION_BLOCKS` value (e.g., 12) from the latest block number. Events are only considered 'final' once they are this many blocks deep.

4.  **Scan Block Range**: It identifies a range of blocks to scan, from `last_processed_block + 1` up to the `latest_block - CONFIRMATION_BLOCKS`.

5.  **Filter for Events**: It uses the `web3.py` library to efficiently filter this block range for any `DepositMade` events emitted by the source bridge contract.

6.  **Process Events**: If events are found, it iterates through each one and passes it to the `TransactionProcessor`.

7.  **Simulate Minting**: The `TransactionProcessor` builds and signs a `mintBridgedTokens` transaction for the destination chain. It logs the details of this simulated transaction, including its potential hash.

8.  **Update and Persist State**: After successfully scanning the block range, the listener updates its `last_processed_block` variable to the end of that range and writes this new value to `bridge_listener_state.json`.

9.  **Wait**: The listener then sleeps for a configured `POLL_INTERVAL_SECONDS` before starting the loop again from step 2.

## Usage Example

Follow these steps to run the simulation.

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd project-chronos
    ```

2.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create a configuration file:**
    Create a file named `.env` in the root of the project and populate it with the required details. You will need RPC URLs (e.g., from Infura or Alchemy) and dummy addresses/keys for the simulation.

    ```dotenv
    # .env file
    
    # Source Chain (e.g., Ethereum Mainnet or a Testnet like Sepolia)
    SOURCE_CHAIN_RPC_URL="https://sepolia.infura.io/v3/YOUR_INFURA_PROJECT_ID"
    SOURCE_CHAIN_BRIDGE_CONTRACT_ADDRESS="0x........................................"
    
    # Destination Chain (e.g., Polygon Mainnet or a Testnet like Mumbai)
    DESTINATION_CHAIN_RPC_URL="https://polygon-mumbai.infura.io/v3/YOUR_INFURA_PROJECT_ID"
    DESTINATION_CHAIN_MINT_CONTROLLER_ADDRESS="0x........................................"
    
    # Private key for the account that will sign the minting transactions on the destination chain
    # IMPORTANT: Use a key from a test/burner wallet for this simulation. DO NOT USE A REAL KEY WITH ASSETS.
    SIGNER_PRIVATE_KEY="0x.............................................................."
    
    # --- Optional Settings ---
    # Number of blocks to wait for confirmation
    CONFIRMATION_BLOCKS=12
    # How often to check for new blocks (in seconds)
    POLL_INTERVAL_SECONDS=15
    # External API for gas price fallback (example for Polygon)
    GAS_STATION_API_URL="https://api.polygonscan.com/api?module=gastracker&action=gasoracle&apikey=YOUR_POLYGONSCAN_API_KEY"
    ```

5.  **Run the script:**
    ```bash
    python script.py
    ```

6.  **Observe the output:**
    The console will show logs detailing the listener's activity, such as the blocks it is scanning, any events it finds, and the steps of the simulated minting process.

    ```
    2023-10-27 15:30:00 - INFO - [script.main] - --- Cross-Chain Bridge Event Listener Started ---
    2023-10-27 15:30:00 - INFO - [script.BridgeEventListener] - Watching for 'DepositMade' events on contract: 0x...
    2023-10-27 15:30:02 - INFO - [script.BridgeEventListener] - Scanning for events from block 4500124 to 4500150...
    2023-10-27 15:30:05 - INFO - [script.BridgeEventListener] - Found 1 new 'DepositMade' event(s).
    2023-10-27 15:30:05 - INFO - [script.TransactionProcessor] - Processing new deposit event: 0x...-12
    2023-10-27 15:30:05 - INFO - [script.TransactionProcessor] -   -> Recipient: 0x..., Amount: 1000000000000000000
    2023-10-27 15:30:05 - INFO - [script.TransactionProcessor] - Simulating mint transaction on destination chain...
    2023-10-27 15:30:06 - INFO - [script.TransactionProcessor] -   -> [SIMULATED] Transaction sent. Hash: 0x...
    2023-10-27 15:30:06 - INFO - [script.TransactionProcessor] -   -> [SIMULATED] Waiting for confirmation...
    2023-10-27 15:30:08 - INFO - [script.TransactionProcessor] -   -> [SUCCESS] Mint for event 0x...-12 confirmed on destination chain.
    2023-10-27 15:30:10 - INFO - [script.BridgeEventListener] - Scanning for events from block 4500151 to 4500165...
    2023-10-27 15:30:12 - INFO - [script.BridgeEventListener] - No new events found in this range.
    ```
