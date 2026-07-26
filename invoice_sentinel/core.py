from __future__ import annotations

import json
import os
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlencode
from uuid import uuid4

from solders.keypair import Keypair
from solders.pubkey import Pubkey

LAMPORTS_PER_SOL = Decimal("1000000000")
DEFAULT_RPC = "https://api.devnet.solana.com"
DEFAULT_DATA_FILE = Path("data/invoices.json")


class SentinelError(RuntimeError):
    """A safe, user-facing validation or RPC error."""


@dataclass
class Invoice:
    id: str
    recipient: str
    amount: str
    asset: str
    reference: str
    label: str
    message: str
    memo: str
    cluster: str
    status: str
    created_at: str
    paid_at: Optional[str] = None
    signature: Optional[str] = None

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "Invoice":
        return cls(**value)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_amount(raw: str) -> Decimal:
    try:
        amount = Decimal(raw)
    except InvalidOperation as exc:
        raise SentinelError("amount must be a decimal number") from exc
    if not amount.is_finite() or amount <= 0:
        raise SentinelError("amount must be greater than zero")
    if amount.as_tuple().exponent < -9:
        raise SentinelError("amount supports at most 9 decimal places")
    return amount


def parse_pubkey(raw: str, field: str) -> str:
    try:
        return str(Pubkey.from_string(raw))
    except ValueError as exc:
        raise SentinelError(f"{field} must be a valid Solana public key") from exc


def normalize_asset(asset: str) -> str:
    if asset.upper() == "SOL":
        return "SOL"
    return parse_pubkey(asset, "asset mint")


def build_solana_pay_uri(invoice: Invoice) -> str:
    params = {
        "amount": invoice.amount,
        "reference": invoice.reference,
        "label": invoice.label,
        "message": invoice.message,
        "memo": invoice.memo,
    }
    if invoice.asset != "SOL":
        params["spl-token"] = invoice.asset
    return f"solana:{invoice.recipient}?{urlencode(params)}"


class InvoiceStore:
    def __init__(self, path: Path = DEFAULT_DATA_FILE):
        self.path = path

    def load(self) -> List[Invoice]:
        if not self.path.exists():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SentinelError(f"cannot read invoice store: {exc}") from exc
        if not isinstance(value, list):
            raise SentinelError("invoice store must contain a JSON array")
        return [Invoice.from_dict(item) for item in value]

    def save(self, invoices: Iterable[Invoice]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            [asdict(invoice) for invoice in invoices],
            indent=2,
            sort_keys=True,
        )
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.write("\n")
            os.replace(temporary_name, self.path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise

    def create(
        self,
        *,
        recipient: str,
        amount: str,
        asset: str,
        label: str,
        message: str,
        memo: str,
        cluster: str,
    ) -> Invoice:
        parsed_amount = parse_amount(amount)
        invoice_id = f"inv_{uuid4().hex[:12]}"
        invoice = Invoice(
            id=invoice_id,
            recipient=parse_pubkey(recipient, "recipient"),
            amount=format(parsed_amount, "f"),
            asset=normalize_asset(asset),
            reference=str(Keypair().pubkey()),
            label=label.strip()[:80] or "Solana Invoice",
            message=message.strip()[:160],
            memo=memo.strip()[:120] or invoice_id,
            cluster=cluster,
            status="pending",
            created_at=utc_now(),
        )
        invoices = self.load()
        invoices.append(invoice)
        self.save(invoices)
        return invoice

    def get(self, invoice_id: str) -> Invoice:
        for invoice in self.load():
            if invoice.id == invoice_id:
                return invoice
        raise SentinelError(f"invoice not found: {invoice_id}")

    def update(self, updated: Invoice) -> None:
        invoices = self.load()
        for index, invoice in enumerate(invoices):
            if invoice.id == updated.id:
                invoices[index] = updated
                self.save(invoices)
                return
        raise SentinelError(f"invoice not found: {updated.id}")


def rpc_call(rpc_url: str, method: str, params: List[Any]) -> Any:
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode("utf-8")
    request = urllib.request.Request(
        rpc_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SentinelError(f"Solana RPC request failed: {exc}") from exc
    if payload.get("error"):
        raise SentinelError(f"Solana RPC error: {payload['error']}")
    return payload.get("result")


def _account_keys(transaction: Dict[str, Any]) -> List[str]:
    message = transaction["transaction"]["message"]
    keys: List[str] = []
    for value in message.get("accountKeys", []):
        keys.append(value["pubkey"] if isinstance(value, dict) else value)
    return keys


def _verify_sol_transfer(invoice: Invoice, transaction: Dict[str, Any]) -> bool:
    keys = _account_keys(transaction)
    if invoice.reference not in keys or invoice.recipient not in keys:
        return False
    recipient_index = keys.index(invoice.recipient)
    meta = transaction.get("meta") or {}
    if meta.get("err") is not None:
        return False
    pre = meta.get("preBalances") or []
    post = meta.get("postBalances") or []
    if recipient_index >= len(pre) or recipient_index >= len(post):
        return False
    expected = int(parse_amount(invoice.amount) * LAMPORTS_PER_SOL)
    return post[recipient_index] - pre[recipient_index] >= expected


def _token_owner_deltas(
    balances: Iterable[Dict[str, Any]], owner: str, mint: str
) -> Dict[int, Decimal]:
    values: Dict[int, Decimal] = {}
    for balance in balances:
        if balance.get("owner") != owner or balance.get("mint") != mint:
            continue
        index = int(balance["accountIndex"])
        raw = balance.get("uiTokenAmount", {}).get("uiAmountString", "0")
        values[index] = Decimal(raw)
    return values


def _verify_spl_transfer(invoice: Invoice, transaction: Dict[str, Any]) -> bool:
    if invoice.reference not in _account_keys(transaction):
        return False
    meta = transaction.get("meta") or {}
    if meta.get("err") is not None:
        return False
    before = _token_owner_deltas(
        meta.get("preTokenBalances") or [], invoice.recipient, invoice.asset
    )
    after = _token_owner_deltas(
        meta.get("postTokenBalances") or [], invoice.recipient, invoice.asset
    )
    indexes = set(before) | set(after)
    received = sum(
        (after.get(index, Decimal(0)) - before.get(index, Decimal(0)))
        for index in indexes
    )
    return received >= parse_amount(invoice.amount)


def verify_transaction(invoice: Invoice, transaction: Dict[str, Any]) -> bool:
    if invoice.asset == "SOL":
        return _verify_sol_transfer(invoice, transaction)
    return _verify_spl_transfer(invoice, transaction)


def check_invoice(
    store: InvoiceStore,
    invoice_id: str,
    rpc_url: str = DEFAULT_RPC,
) -> Invoice:
    invoice = store.get(invoice_id)
    if invoice.status == "paid":
        return invoice
    signatures = rpc_call(
        rpc_url,
        "getSignaturesForAddress",
        [invoice.reference, {"limit": 20, "commitment": "confirmed"}],
    )
    for row in signatures or []:
        if row.get("err") is not None:
            continue
        signature = row.get("signature")
        transaction = rpc_call(
            rpc_url,
            "getTransaction",
            [
                signature,
                {
                    "commitment": "confirmed",
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        )
        if transaction and verify_transaction(invoice, transaction):
            invoice.status = "paid"
            invoice.signature = signature
            invoice.paid_at = utc_now()
            store.update(invoice)
            return invoice
    return invoice


def verify_invoice_file(
    store: InvoiceStore,
    invoice_id: str,
    transaction_path: Path,
    signature: Optional[str] = None,
) -> Invoice:
    invoice = store.get(invoice_id)
    try:
        payload = json.loads(transaction_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SentinelError(f"cannot read transaction JSON: {exc}") from exc
    transaction = payload.get("result") if isinstance(payload, dict) else None
    if transaction is None:
        transaction = payload
    if not isinstance(transaction, dict):
        raise SentinelError("transaction JSON must contain an object")
    if verify_transaction(invoice, transaction):
        invoice.status = "paid"
        invoice.signature = signature or invoice.signature
        invoice.paid_at = utc_now()
        store.update(invoice)
    return invoice
