import logging
from dataclasses import dataclass

from eth_account import Account
from web3 import Web3

import db

logger = logging.getLogger(__name__)


@dataclass
class IncomingTx:
    from_addr: str
    wei: int
    tx_hash: str


def generate_wallet() -> tuple[str, str]:
    """Generate a new Ethereum keypair. Returns (private_key_hex, address)."""
    acct = Account.create()
    return acct.key.hex(), acct.address


def get_address(private_key: str) -> str:
    acct = Account.from_key(private_key)
    return acct.address


def check_incoming(private_key: str, rpc_url: str) -> list[IncomingTx]:
    """
    Scan for ETH transactions to our wallet since the last checked block.
    Returns a list of incoming transactions found.
    """
    if not rpc_url:
        logger.debug("No ETH_RPC_URL configured — skipping ETH feed check")
        return []

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        logger.warning("Cannot connect to Ethereum RPC: %s", rpc_url)
        return []

    our_address = get_address(private_key).lower()
    last_block = int(db.get_state("eth_last_block", "0"))

    try:
        latest = w3.eth.block_number
    except Exception:
        logger.exception("Failed to fetch latest block number")
        return []

    if last_block == 0:
        # On first run scan only the latest block to avoid massive history scan
        last_block = latest - 1

    results: list[IncomingTx] = []

    # Scan at most 50 blocks per call to avoid timeout
    from_block = last_block + 1
    to_block = min(latest, from_block + 49)

    for block_num in range(from_block, to_block + 1):
        try:
            block = w3.eth.get_block(block_num, full_transactions=True)
        except Exception:
            logger.warning("Could not fetch block %d", block_num)
            continue

        for tx in block.transactions:
            if tx.get("to") and tx["to"].lower() == our_address and tx["value"] > 0:
                results.append(
                    IncomingTx(
                        from_addr=tx["from"],
                        wei=tx["value"],
                        tx_hash=tx["hash"].hex(),
                    )
                )

    db.set_state("eth_last_block", str(to_block))
    return results
