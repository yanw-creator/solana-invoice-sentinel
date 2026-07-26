# Threat model

## Custody tier

Invoice Sentinel is T1 (build, never sign). It creates Solana Pay transfer
requests and reads Solana RPC. It does not store wallet keys, sign
transactions, broadcast transactions, or initiate refunds.

The per-invoice reference is a public key used only to correlate a payment.
The generated reference keypair is discarded immediately; its secret has no
authority and is never stored.

## Assets and trust boundaries

- Merchant recipient and token mint are operator-supplied public keys.
- Customer messages, labels, memos, pasted signatures, screenshots, and RPC
  responses are untrusted.
- The configured RPC is trusted for availability, but payment verification
  checks transaction success, reference membership, recipient, mint, and
  value rather than accepting a signature at face value.
- The local JSON ledger is merchant-owned state. Writes use an atomic
  temporary-file replacement.

## Abuse cases and controls

| Abuse case | Control |
| --- | --- |
| Prompt asks agent to reveal or import a private key | Skill refuses; no signing code exists |
| Customer asks to refund an attacker address | Refunds are outside the tool and human-only |
| Screenshot claims payment | Status changes only after RPC verification |
| Unrelated transaction mentions the reference | Recipient and exact value are checked |
| Failed transaction has plausible balances | `meta.err` must be null |
| Invoice memo contains prompt injection | Content is treated as data and length-bounded |
| Mainnet typo | Agent repeats amount, asset, and recipient for approval |
| RPC outage | Invoice remains pending; failure never becomes success |

## Known limits

- The current checker supports direct SOL transfers and owner-attributed SPL
  token balance changes. Complex routed payments should use a Solana Action
  endpoint with a separate verifier.
- One RPC endpoint is configured at a time. Production operators should add a
  second provider or self-hosted RPC for availability.
- This is payment detection, not accounting, tax, or sanctions software.

