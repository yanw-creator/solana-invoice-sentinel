from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Sequence

from .core import (
    DEFAULT_DATA_FILE,
    DEFAULT_RPC,
    Invoice,
    InvoiceStore,
    SentinelError,
    build_solana_pay_uri,
    check_invoice,
)


def emit(invoice: Invoice, *, uri: bool = False) -> None:
    value = asdict(invoice)
    if uri:
        value["solana_pay_uri"] = build_solana_pay_uri(invoice)
    print(json.dumps(value, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="invoice-sentinel",
        description="Create non-custodial Solana Pay invoices and verify receipts.",
    )
    parser.add_argument(
        "--data-file",
        type=Path,
        default=DEFAULT_DATA_FILE,
        help="JSON invoice store (default: data/invoices.json)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="create a payment request")
    create.add_argument("--recipient", required=True)
    create.add_argument("--amount", required=True)
    create.add_argument("--asset", default="SOL", help="SOL or an SPL token mint")
    create.add_argument("--label", default="Solana Invoice")
    create.add_argument("--message", default="")
    create.add_argument("--memo", default="")
    create.add_argument(
        "--cluster",
        choices=["devnet", "mainnet-beta"],
        default="devnet",
    )
    create.add_argument("--qr", type=Path, help="optional PNG output path")

    status = subparsers.add_parser("status", help="show a saved invoice")
    status.add_argument("invoice_id")

    check = subparsers.add_parser(
        "check",
        help="verify a payment against Solana RPC",
    )
    check.add_argument("invoice_id")
    check.add_argument("--rpc", default=DEFAULT_RPC)

    verify_file = subparsers.add_parser(
        "verify-file",
        help="verify a getTransaction JSON response saved by ZeroClaw HTTP",
    )
    verify_file.add_argument("invoice_id")
    verify_file.add_argument("transaction_json", type=Path)
    verify_file.add_argument("--signature")

    subparsers.add_parser("list", help="list saved invoices")
    return parser


def write_qr(uri: str, output: Path) -> None:
    try:
        import qrcode
    except ImportError as exc:
        raise SentinelError("QR output requires the qrcode package") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    image = qrcode.make(uri)
    image.save(output)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    store = InvoiceStore(args.data_file)
    try:
        if args.command == "create":
            invoice = store.create(
                recipient=args.recipient,
                amount=args.amount,
                asset=args.asset,
                label=args.label,
                message=args.message,
                memo=args.memo,
                cluster=args.cluster,
            )
            uri = build_solana_pay_uri(invoice)
            if args.qr:
                write_qr(uri, args.qr)
            emit(invoice, uri=True)
        elif args.command == "status":
            emit(store.get(args.invoice_id), uri=True)
        elif args.command == "check":
            emit(check_invoice(store, args.invoice_id, args.rpc), uri=True)
        elif args.command == "verify-file":
            from .core import verify_invoice_file

            emit(
                verify_invoice_file(
                    store,
                    args.invoice_id,
                    args.transaction_json,
                    args.signature,
                ),
                uri=True,
            )
        elif args.command == "list":
            print(
                json.dumps(
                    [asdict(invoice) for invoice in store.load()],
                    indent=2,
                    sort_keys=True,
                )
            )
        return 0
    except SentinelError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
