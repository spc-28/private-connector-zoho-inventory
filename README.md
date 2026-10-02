# Zoho Inventory Connector for Agent Studio

Assignment: Option 3.

A read-only MCP server that lets Agent Studio agents look up a merchant's Zoho Inventory orders, shipments and stock, and build dispute evidence.

## Setup

You need Python 3.12, [uv](https://docs.astral.sh/uv/), and a Zoho Inventory organization (the Free plan works).

1. Install:
   ```bash
   uv venv --python 3.12 .venv
   uv pip install --python .venv/bin/python -e ".[dev,evals]"
   ```
2. In the Zoho API Console, create a **Server-based Application** with redirect URI `http://127.0.0.1:8765/callback`, and turn on Multi-DC.
3. Copy `.env.example` to `.env`, then fill in `ZOHO_CLIENT_ID` and `ZOHO_CLIENT_SECRET`. Set `ZOHO_ACCOUNTS_URL` to your region, for example `https://accounts.zoho.in`.
4. Authorize (opens a browser):
   ```bash
   .venv/bin/zoho-connector-setup
   ```
5. Check which Zoho filters work:
   ```bash
   .venv/bin/python scripts/spike_filters.py
   ```
6. Run the server:
   ```bash
   .venv/bin/zoho-connector
   ```

## Demo data (optional)

Create a Zoho **Self Client**, then fill in the `ZOHO_SEED_*` values in `.env`. To list the scopes needed for the grant code, run:

```bash
.venv/bin/python scripts/seed_data.py --help
.venv/bin/python scripts/seed_data.py --code GRANT_CODE
```

## Checks

```bash
(cd scripts && ../.venv/bin/python smoke_test.py)      # every tool, live
(cd scripts && ../.venv/bin/python limiter_drill.py)   # rate-limit handling
.venv/bin/python evals/run_evals.py                    # agent evals, needs ANTHROPIC_API_KEY
```

## Assumptions

- The merchant stores the Razorpay payment ID in the sales order's Reference# field. A different field can be set with `ZOHO_PAYMENT_LINK_FIELD`.
- The merchant records shipments in Zoho with a carrier and tracking number.
- The agent runtime can connect to an MCP server over stdio.
- The Zoho Free plan's API quota is enough for the demo.
- Only fictional seeded data is used. No real customer data is involved.

## Limitations

- **Read-only.** The connector never changes Zoho and never calls Razorpay. It prepares evidence; a person or the Dispute Responder agent decides whether to contest and submits.
- **No delivery date.** Zoho holds a delivery status, not a carrier-confirmed delivery date. Proof of delivery has to come from the carrier, using the tracking number.
- **One organization, local only.** It serves one Zoho organization over stdio. A hosted Agent Studio deployment would need an HTTP transport.
- **Not real-time.** There are no webhooks, so data is as fresh as the last call.
- **Partial dispute coverage.** "Product not received" is covered fully, and fraud and duplicate disputes in part. Refund and "not as described" disputes are not covered.
- **Some evidence lives elsewhere.** Customer messages, refund policies and access logs are not in Zoho. The evidence pack lists them as gaps.
- **Order search depends on Zoho.** Zoho does not document its order search filters. The day-0 check decides which ones are used; any others are applied inside the connector, over the most recent 2,000 orders at most.
- **Privacy trade-off on documents.** Customer emails and phone numbers are masked in everything the agent sees. Exported invoice and package-slip PDFs carry full details, stay on the local machine, and are deleted after 7 days.
- **No unit tests.** Quality is checked with the live smoke test, the rate-limit drill and the agent evals instead.
