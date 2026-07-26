"""Create, pay, and verify a disposable devnet invoice.

This file is demo-only. It creates fresh session keypairs, requests devnet SOL,
and sends exactly one bounded transfer. No key is written to disk.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from solana.rpc.api import Client
from solana.rpc.core import RPCException
from solana.exceptions import SolanaRpcException
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.system_program import TransferParams, transfer
from solders.transaction import VersionedTransaction

from invoice_sentinel.core import InvoiceStore, build_solana_pay_uri, check_invoice

RPC_URLS = [
    "https://api.devnet.solana.com",
    "https://solana-devnet-rpc.publicnode.com",
]
LAMPORTS = 10_000_000


def funded_client(payer: Keypair) -> Tuple[Client, str]:
    failures = []
    for rpc_url in RPC_URLS:
        client = Client(rpc_url)
        try:
            airdrop = client.request_airdrop(payer.pubkey(), 20_000_000).value
            client.confirm_transaction(airdrop, commitment="confirmed")
            return client, rpc_url
        except (RPCException, SolanaRpcException, OSError, ValueError) as exc:
            failures.append(f"{rpc_url}: {exc}")
    raise RuntimeError(
        "All public devnet faucets refused the disposable wallet. "
        "Retry later; no real funds are required.\n" + "\n".join(failures)
    )


def main() -> None:
    payer = Keypair()
    recipient = Keypair()
    store = InvoiceStore(Path("demo-output/devnet-invoices.json"))
    invoice = store.create(
        recipient=str(recipient.pubkey()),
        amount="0.01",
        asset="SOL",
        label="Invoice Sentinel Demo",
        message="Disposable devnet round trip",
        memo="DEMO-ROUND-TRIP",
        cluster="devnet",
    )

    client, rpc_url = funded_client(payer)

    base_instruction = transfer(
        TransferParams(
            from_pubkey=payer.pubkey(),
            to_pubkey=recipient.pubkey(),
            lamports=LAMPORTS,
        )
    )
    reference = AccountMeta(
        pubkey=type(recipient.pubkey()).from_string(invoice.reference),
        is_signer=False,
        is_writable=False,
    )
    referenced_transfer = Instruction(
        base_instruction.program_id,
        base_instruction.data,
        [*base_instruction.accounts, reference],
    )
    blockhash = client.get_latest_blockhash(commitment="confirmed").value.blockhash
    message = MessageV0.try_compile(
        payer.pubkey(),
        [referenced_transfer],
        [],
        blockhash,
    )
    transaction = VersionedTransaction(message, [payer])
    signature = client.send_transaction(transaction).value
    client.confirm_transaction(signature, commitment="confirmed")

    verified = check_invoice(store, invoice.id, rpc_url)
    print(
        json.dumps(
            {
                "invoice": asdict(verified),
                "solana_pay_uri": build_solana_pay_uri(verified),
                "devnet_signature": str(signature),
                "explorer": (
                    f"https://explorer.solana.com/tx/{signature}?cluster=devnet"
                ),
                "session_keys_persisted": False,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
