# Solana Invoice Sentinel

A self-hosted ZeroClaw payment clerk that creates uniquely referenced Solana
Pay invoices and verifies receipts without ever holding a wallet key.

The use case is deliberately boring infrastructure: a merchant asks for an
invoice, the agent returns a Solana Pay URI and QR, and later checks the chain.
The payer signs in their wallet. Refunds remain human-only.

## Why it exists

LLMs are useful at turning chat into structured workflows, but an LLM with a
private key is a hot wallet with a prompt-injection surface. Invoice Sentinel
keeps the conversational convenience and removes custody:

- T1 custody: build and verify, never sign;
- exact recipient, asset, amount, and unique reference checks;
- screenshots and pasted signatures cannot mark an invoice paid;
- local, atomic invoice ledger;
- fail-closed handling for RPC errors and malicious refund instructions.

## Quick start

Requirements: Python 3.9+ and a ZeroClaw 0.8.x binary.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
   .venv/bin/python scripts/invoice_sentinel.py create \
  --recipient YOUR_SOLANA_PUBLIC_KEY \
  --amount 0.01 \
  --asset SOL \
  --label "Demo Shop" \
  --message "Order 42" \
  --memo "ORDER-42" \
  --cluster devnet \
  --qr demo-output/invoice.png
```

The command prints JSON containing the invoice ID and Solana Pay URI. Check it:

```sh
.venv/bin/python scripts/invoice_sentinel.py check INV_ID \
  --rpc https://api.devnet.solana.com
```

## ZeroClaw setup

1. Install ZeroClaw and import an existing Codex login:

   ```sh
   zeroclaw auth login \
     --model-provider openai-codex \
     --import ~/.codex/auth.json
   ```

2. Copy `config/zeroclaw.example.toml` to the ZeroClaw config directory and
   replace both absolute placeholder paths.
3. Run `zeroclaw skills audit skills/invoice-sentinel`.
4. Start the real CLI channel:

   ```sh
   zeroclaw agent -a sentinel
   ```

5. Ask:

   ```text
   Create a devnet invoice for 0.01 SOL to <recipient> for Order 42.
   ```

ZeroClaw's supervised profile asks the operator to approve the bounded Python
command. The agent returns the generated request; it never sees a private key.

## Demo story

1. Merchant asks the ZeroClaw CLI agent for an invoice.
2. Agent proposes the exact command; merchant approves.
3. Invoice Sentinel creates an ID, reference public key, Solana Pay URI, and QR.
4. A disposable devnet payer pays the invoice.
5. Merchant asks the agent to check status.
6. The verifier reads the reference address, fetches the transaction, and
   checks success, recipient, asset, and amount before returning `paid`.
7. A malicious customer message asks for a refund to another address. The
   agent refuses because refunds and signing do not exist in this skill.

## Tests

```sh
.venv/bin/python -m pytest
```

The tests cover amount validation, URI/reference generation, persistence,
successful SOL receipt verification, underpayment rejection, and failed
transaction rejection. Inside ZeroClaw, public RPC calls use the bounded
built-in HTTP tool and the Python checker verifies the saved response offline;
the OS sandbox remains enabled.

For a real devnet round trip with disposable in-memory keys:

```sh
.venv/bin/python -m pip install -r requirements-demo.txt
.venv/bin/python demo/devnet_round_trip.py
```

The script requests devnet SOL, sends one 0.01 SOL transfer containing the
invoice reference, verifies it through public RPC, and prints the explorer URL.
Devnet SOL has no monetary value. Faucet rate limits can make the demo
temporarily unavailable.

## Security

Read [the threat model](docs/threat-model.md). This software is an educational
reference and not financial, legal, or tax advice. Use devnet first.

Public demos and submissions must also follow [the privacy and redaction
policy](PRIVACY.md).

## License

MIT
