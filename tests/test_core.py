from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from solders.keypair import Keypair

from invoice_sentinel.core import (
    InvoiceStore,
    SentinelError,
    build_solana_pay_uri,
    parse_amount,
    verify_invoice_file,
    verify_transaction,
)


def pubkey() -> str:
    return str(Keypair().pubkey())


def test_amount_validation() -> None:
    assert parse_amount("1.25") == Decimal("1.25")
    for value in ["0", "-1", "nan", "0.0000000001"]:
        with pytest.raises(SentinelError):
            parse_amount(value)


def test_invoice_uri_and_persistence(tmp_path: Path) -> None:
    store = InvoiceStore(tmp_path / "invoices.json")
    invoice = store.create(
        recipient=pubkey(),
        amount="0.01",
        asset="SOL",
        label="Corner Shop",
        message="Table 4",
        memo="ORDER-4",
        cluster="devnet",
    )
    uri = build_solana_pay_uri(invoice)
    parsed = urlsplit(uri)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "solana"
    assert parsed.path == invoice.recipient
    assert query["amount"] == ["0.01"]
    assert query["reference"] == [invoice.reference]
    assert store.get(invoice.id) == invoice


def test_sol_payment_requires_reference_recipient_and_amount(tmp_path: Path) -> None:
    store = InvoiceStore(tmp_path / "invoices.json")
    invoice = store.create(
        recipient=pubkey(),
        amount="0.5",
        asset="SOL",
        label="Shop",
        message="Order",
        memo="ORDER-1",
        cluster="devnet",
    )
    keys = [pubkey(), invoice.recipient, invoice.reference]
    transaction = {
        "transaction": {
            "message": {
                "accountKeys": [{"pubkey": key} for key in keys],
            }
        },
        "meta": {
            "err": None,
            "preBalances": [2_000_000_000, 1_000_000_000, 0],
            "postBalances": [1_499_995_000, 1_500_000_000, 0],
        },
    }

    assert verify_transaction(invoice, transaction)
    transaction["meta"]["postBalances"][1] = 1_499_999_999
    assert not verify_transaction(invoice, transaction)


def test_failed_transaction_is_never_payment(tmp_path: Path) -> None:
    store = InvoiceStore(tmp_path / "invoices.json")
    invoice = store.create(
        recipient=pubkey(),
        amount="0.1",
        asset="SOL",
        label="Shop",
        message="Order",
        memo="ORDER-2",
        cluster="devnet",
    )
    transaction = {
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": invoice.recipient},
                    {"pubkey": invoice.reference},
                ]
            }
        },
        "meta": {
            "err": {"InstructionError": [0, "Custom"]},
            "preBalances": [0, 0],
            "postBalances": [1_000_000_000, 0],
        },
    }
    assert not verify_transaction(invoice, transaction)


def test_verify_file_marks_only_valid_transaction_paid(tmp_path: Path) -> None:
    store = InvoiceStore(tmp_path / "invoices.json")
    invoice = store.create(
        recipient=pubkey(),
        amount="0.25",
        asset="SOL",
        label="Shop",
        message="Order",
        memo="ORDER-3",
        cluster="devnet",
    )
    keys = [pubkey(), invoice.recipient, invoice.reference]
    transaction = {
        "result": {
            "transaction": {
                "message": {
                    "accountKeys": [{"pubkey": key} for key in keys],
                }
            },
            "meta": {
                "err": None,
                "preBalances": [1_000_000_000, 0, 0],
                "postBalances": [749_995_000, 250_000_000, 0],
            },
        }
    }
    path = tmp_path / "transaction.json"
    path.write_text(__import__("json").dumps(transaction), encoding="utf-8")

    verified = verify_invoice_file(store, invoice.id, path, "test-signature")
    assert verified.status == "paid"
    assert verified.signature == "test-signature"
