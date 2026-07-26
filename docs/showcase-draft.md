# Showcase draft

**Repository:** https://github.com/yanw-creator/solana-invoice-sentinel

**88-second demo:** https://youtu.be/3Micbe0qQFI

## What it does

Invoice Sentinel turns a merchant request into a uniquely referenced Solana Pay
invoice, produces a scannable QR, and verifies the receipt against Solana RPC.
It runs as a ZeroClaw skill. The agent owns no wallet key and cannot refund or
send funds.

## Who it is for

Small merchants, event booths, community treasuries, and self-hosters who want
chat-native stablecoin or SOL invoicing without turning an LLM into a hot
wallet.

## ZeroClaw features used

- local skill bundle for the payment workflow and reply contract;
- supervised risk profile and workspace jail;
- CLI channel for a reproducible local demo;
- persistent agent workspace and local invoice ledger;
- operator approval before shell execution;
- OpenAI Codex subscription provider imported through ZeroClaw auth.

## Reproduction

See the repository README. The demo uses devnet and a disposable test payer.
No real funds or wallet secrets are required.

## Custody and safety

T1. The agent builds a Solana Pay URL and reads RPC. The wallet owner signs.
The agent has no code path for signing, broadcasting, or refunding. A malicious
customer prompt asking it to ignore policy and refund to another address is
refused; the transcript is included in `docs/prompt-injection-transcript.md`.

## Verified demo evidence

- ZeroClaw 0.8.3 skill audit: passed.
- Python verification suite: 5 tests passed.
- Real ZeroClaw CLI invoice creation: passed with one-time shell approval.
- QR generated at `demo-output/zeroclaw-invoice.png`.
- Prompt-injection refund/seed-phrase request: refused with no tool call.
- Bounded Solana devnet RPC check: passed and correctly returned `pending`.
- Disposable devnet payment helper: implemented; public faucets were
  rate-limited during the recorded run, so no paid transaction is claimed.
