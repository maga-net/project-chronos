# Project Chronos: Cross-Chain Bridge Oracle Simulation

This repository contains a Python-based simulation of an off-chain oracle/validator component for a cross-chain asset bridge. The script demonstrates the architectural patterns and logic required to monitor events on a source blockchain and trigger corresponding actions on a destination blockchain.

## Concept

A cross-chain bridge allows users to transfer assets from one blockchain (e.g., Ethereum) to another (e.g., Polygon). A common mechanism is the "lock-and-mint" model:

1.  **Lock**: A user locks their assets (e.g., WETH) in a smart contract on the source chain.
2.  **Event Emission**: The smart contract emits an event (`TokensLocked`) containing details of the deposit.
3.  **Oracle Validation**: Off-chain services, known as oracles or relayers, listen for this event. They verify its authenticity and validity (e.g., check the amount, prevent replay attacks).
4.  **Mint**: Upon successful validation, the oracle submits a signed transaction to a smart contract on the destination chain.
5.  **Wrapped Asset Creation**: The destination contract mints a corresponding "wrapped" asset (e.g., pWETH) and sends it to the user's address on the new chain.

**Project Chronos simulates the critical off-chain component (steps 3 and 4) of this system.**

## Code Architecture

The script is designed with a modular, object-oriented approach to separate concerns and enhance maintainability.

```
+-----------------------+
|      BridgeOracle     | (Main Orchestrator)
+-----------+-----------+
            |
            | 1. Starts & manages the loop
            | 5. Updates & persists state
            v
.-----------+-------------------------------------------------------------.
|           |                            |                                |
|           v                            v                                v
| +------------------------+   +----------------------+   +-------------------------+ |
| |BridgeContractEventHandler|   | TransactionValidator |   | DestinationChainMinter  | |
| +------------------------+   +----------------------+   +-------------------------+ |
| | - Scans block ranges   |   | - Checks for replays |   | - Builds mint tx        | |
| | - Fetches event logs   |   | - Validates amounts  |   | - Signs tx (simulated)  | |
| |                        |   | - Checks token       |   | - Submits tx (simulated)| |
| '-----------+------------'   '----------+-----------'   '------------+------------' |
|             |                          |                              |
|             v                          |                              |
| +------------------------+             |                              v
| |   BlockchainConnector  | <-----------+----------------> +------------------------+ |
| |    (Source Chain)      |                                |   BlockchainConnector  | |
| +------------------------+                                +------------------------+ |
| | - Connects to RPC      |                                |    (Destination Chain)  | |
| | - Provides web3 obj    |                                '------------------------' |
| '------------------------'                                                             |
'---------------------------------------------------------------------------------------'
```

-   **`BlockchainConnector`**: A reusable class that manages the connection to a blockchain's RPC endpoint using `web3.py`. It provides a `Web3` instance and helpers to get contract objects.

-   **`BridgeContractEventHandler`**: Responsible for scanning block ranges on the source chain, filtering for the `TokensLocked` event, and returning the decoded event data.

-   **`TransactionValidator`**: Performs crucial security and business logic checks on fetched event data. This includes preventing replay attacks by tracking transaction IDs and validating the transaction value against configured limits using an external `requests` call to a price oracle API (e.g., CoinGecko).

-   **`DestinationChainMinter`**: Simulates the final step. Once an event is validated, this class constructs, signs, and (in this simulation) logs the details of the transaction that would be sent to the destination chain to mint the wrapped assets.

-   **`BridgeOracle`**: The main class that orchestrates the entire workflow. It initializes all other components, manages the main processing loop, handles state (e.g., the last block number processed), and ensures continuous operation.

## How it Works

The script executes a continuous loop with the following steps:

1.  **State Initialization**: The `BridgeOracle` loads its state from a local file (`oracle_state.json`), which contains the last block number it successfully processed. If the file doesn't exist, it starts from a pre-configured `start_block`.

2.  **Block Range Calculation**: It determines the range of blocks to scan on the source chain, from `last_processed_block + 1` up to the current latest block, processing in manageable chunks (`block_chunk_size`).

3.  **Event Fetching**: The `BridgeContractEventHandler` queries the source chain's RPC node for `TokensLocked` events within the calculated block range.

4.  **Event Processing Loop**: For each event found:
    a. The event data is passed to the `TransactionValidator`.
    b. The validator checks if the transaction ID has been seen before. It then fetches the token's current price and verifies that the transaction value is within acceptable minimum and maximum limits.
    c. If validation is successful, the event data is passed to the `DestinationChainMinter`.
    d. The `DestinationChainMinter` simulates the creation and signing of a `mintWrappedTokens` transaction, logging the details of what would be sent to the destination chain.
    e. If validation fails, the event is logged and skipped.

5.  **State Update**: After processing the block range, the `BridgeOracle` updates its state with the last block number it scanned and saves it to `oracle_state.json` to ensure continuity.

6.  **Wait**: The script waits for a configured interval (`poll_interval_seconds`) before starting the next cycle, preventing RPC rate-limiting and unnecessary resource consumption.

## Usage

### 1. Prerequisites

-   Python 3.8+
-   Access to source and destination blockchain RPC URLs (e.g., from Alchemy, Infura, or a local node). The simulation is configured for Sepolia (source) and Mumbai (destination).

### 2. Installation

Clone the repository and install the required dependencies:

```bash
git clone https://github.com/your-username/project-chronos.git
cd project-chronos
pip install -r requirements.txt
```

### 3. Configuration

Create a `.env` file in the project's root directory. This file is git-ignored to protect your secrets. Copy the following template and fill in your values:

```dotenv
# .env.example

# RPC URL for the source chain (e.g., Ethereum Sepolia)
SOURCE_CHAIN_RPC_URL="https://eth-sepolia.g.alchemy.com/v2/YOUR_ALCHEMY_API_KEY"

# RPC URL for the destination chain (e.g., Polygon Mumbai)
DESTINATION_CHAIN_RPC_URL="https://polygon-mumbai.g.alchemy.com/v2/YOUR_ALCHEMY_API_KEY"

# Private key of the oracle's wallet. Must start with 0x.
# WARNING: Use a dedicated key with limited funds, especially for development.
ORACLE_PRIVATE_KEY="0x..."
```

### 4. Running the Script

Execute the main script from your terminal:

```bash
python oracle_simulation.py
```

### 5. Sample Output

The script will start logging its operations to the console. When it finds and processes an event, the output will look similar to this:

```
2023-10-27 14:30:10 - [INFO] - BridgeOracle - --- Project Chronos Oracle starting up ---
2023-10-27 14:30:11 - [INFO] - BlockchainConnector[Ethereum-Sepolia] - Successfully connected to Ethereum-Sepolia. Chain ID: 11155111
2023-10-27 14:30:12 - [INFO] - BlockchainConnector[Polygon-Mumbai] - Successfully connected to Polygon-Mumbai. Chain ID: 80001
2023-10-27 14:30:12 - [INFO] - Minter[Polygon-Mumbai] - Minter initialized for account: 0xYourOracleWalletAddress
2023-10-27 14:30:12 - [INFO] - BridgeOracle - Loaded state from oracle_state.json: {'last_processed_block': 19000000}
2023-10-27 14:30:15 - [INFO] - BridgeOracle - Scanning for events from block 19000001 to 19000100...
2023-10-27 14:30:18 - [INFO] - EventHandler[Ethereum-Sepolia] - Found 1 'TokensLocked' event(s) between blocks 19000001-19000100.
2023-10-27 14:30:18 - [INFO] - BridgeOracle - Processing event from transaction: 0x123abc...def456
2023-10-27 14:30:18 - [INFO] - TransactionValidator - Validating transaction ID: 0xabc...def
2023-10-27 14:30:19 - [INFO] - TransactionValidator - Transaction abc...def details: 0.5 WETH (~$950.45)
2023-10-27 14:30:19 - [INFO] - TransactionValidator - Transaction abc...def passed all validation checks.
2023-10-27 14:30:19 - [INFO] - Minter[Polygon-Mumbai] - Preparing to mint 0.5 tokens for 0xSenderAddress on Polygon-Mumbai.
2023-10-27 14:30:20 - [INFO] - Minter[Polygon-Mumbai] - [SIMULATION] Transaction to mint tokens would be sent now.
2023-10-27 14:30:20 - [INFO] - Minter[Polygon-Mumbai] - [SIMULATION]   - To: 0x000000000000000000000000000000000000dEaD
2023-10-27 14:30:20 - [INFO] - Minter[Polygon-Mumbai] - [SIMULATION]   - Function: mintWrappedTokens(recipient=0xSenderAddress, amount=500000000000000000, sourceTransactionId=0xabc...def)
2023-10-27 14:30:20 - [INFO] - Minter[Polygon-Mumbai] - [SIMULATION]   - Signed TX Hash (raw): 0x789ghi...jkl789
```