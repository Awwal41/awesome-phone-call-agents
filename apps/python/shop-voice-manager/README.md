# Voice Shop Manager (Python demo)

**Your business manager, on the phone** — demo build for the CALL-E hackathon.

Voice-first check-ins for informal retailers: morning inventory and evening sales captured by CALL-E, structured into JSON, summarized into weekly business insights.

> **Demo mode:** This app runs **without** a live phone call or API key by default. Fixtures simulate completed calls so judges and collaborators can run the flow locally.

## Setup

Python 3.11 or newer. No API key is needed for the demo path.

```bash
cd apps/python/shop-voice-manager
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install pytest jsonschema    # only needed to run the tests
```

Credentials, when live calls land (R5), come from the environment or a local
`.env` — never from a committed file.

## Quick start (demo — no CALL-E credits)

```bash
cd apps/python/shop-voice-manager
python client.py --request example_request.json
python client.py --request example_request_sales.json
python client.py --request example_request.json --weekly-summary
```

Expected: masked preview plan + fixture structured result. No network.

`--weekly-summary` is **computed, not canned**. The fixture call results are
ingested into a real SQLite ledger and `summarize.py` derives every figure from
it — change a fixture and the numbers change. Add `--slow-moving-method
top-sellers` to compare the two ways of identifying dead stock.

## Live calls (opt-in — R5, implemented)

A real call needs **both** flags, plus a key. Any one missing exits `2` without
building a client:

```bash
export CALLE_API_KEY=...                    # never commit this
python client.py --request my-live-request.json \
    --execute --confirm-recipient-opt-in \
    --db shop.db                            # optional: ingest the result
```

Refusals, all before anything dials:

| Situation | Result |
| --- | --- |
| `--execute` without `--confirm-recipient-opt-in` | exit 2 |
| `recipient_consented` not `true` in the request | exit 2 |
| `CALLE_API_KEY` unset | exit 2 |
| `CALLE_BASE_URL` not `https://api.heycall-e.com` | exit 1 |
| `--live` (the old spelling) | exit 2, tells you the new flags |

**One call per shop per type per day.** The idempotency key is
`shopvoice-{shop_id}-{call_type}-{date}` and a checkpoint under `.call-state/`
records the call id the moment CALL-E returns one — so a crash mid-call, or a
rerun, **polls the existing call instead of placing a second**. Checkpoints
store a masked phone and a hash of the key, never the key or the full number.

The result is handed to the same `ingest.ingest_call` the fixtures go through,
so a live call faces the identical confidence gate. See
`skills/shop-voice-checkin/references/safety.md`.

## Side effects

| Mode | Network | Phone call | Credits |
| --- | --- | --- | --- |
| Default / `--fixture` / `--weekly-summary` | No | No | 0 |
| `pytest` | No | No | 0 |
| `--execute --confirm-recipient-opt-in` | Yes | **Yes** | 1 per call |

## Files

| File | Purpose |
| --- | --- |
| `example_request.json` | Morning inventory demo request (masked phone) |
| `example_request_sales.json` | Evening sales demo request |
| `fixtures/` | Fictional transcripts and structured results, plus a full week of calls, edge cases, and golden summaries |
| `client.py` | Demo runner |
| `summarize.py` | Weekly business insights, computed from the ledger (AR2) |
| `store.py` | SQLite ledger — schema, migrations, and the four write paths (R4) |
| `ingest.py` | Turns a CALL-E result into ledger rows; confidence-gated, idempotent (R6) |
| `demo_ledger.py` | Feeds the fixtures through `ingest.py` → `store.py`. Only the input is fake — the write path is the production one |
| `live_call.py` | The live CALL-E path (R5): trusted-host check, consent check, crash-safe checkpoints, result normalisation |
| `SCHEMA.md` | The ledger contract both sides build against |
| `tests/` | 42 tests. No credentials, no network, no calls |

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests -q                     # 67 tests
python fixtures/validate_fixtures.py
```

Individual suites:

```bash
pytest tests/test_live_call.py -q   # 25 tests — the live path, fully stubbed
pytest tests/test_store_ingest.py -q
pytest tests/test_summarize.py -q
pytest tests/test_no_live_calls.py -q
```

`tests/test_live_call.py` covers R5 without the SDK installed and without a
credential — it drives `execute_live` with a stub client that records every
`create`, so "did we place two calls?" is an assertion rather than a hope. Run
it after any change to `live_call.py`; it is the only thing standing between a
refactor and a duplicate call. To see one test's reasoning:

```bash
pytest tests/test_live_call.py::test_rerun_after_a_crash_polls_instead_of_calling_again -v
```

`tests/test_no_live_calls.py` scans every test file for anything that could
dial. If you legitimately need to name the CALL-E host in a test — the
allowlist tests do — mark that line `# allow-host-literal` so the exception
stays visible.

Or run everything the pre-push hook runs, from the repository root:

```bash
./check.sh                          # validation + fixtures + tests
```

None of it places a phone call or needs credentials.

## Cancellation

Recurring check-ins are owned by the host scheduler, not this app. To stop them,
see [`scheduling.md`](../../../skills/shop-voice-checkin/references/scheduling.md#cancellation).
Clearing `recipient_consented` alone does **not** stop calls — the scheduler
never reads it.

## Skill

Agent workflow: [`skills/shop-voice-checkin/`](../../skills/shop-voice-checkin/)

## Project plan

[`docs/projects/voice-shop-manager/PROJECT_PLAN.md`](../../../docs/projects/voice-shop-manager/PROJECT_PLAN.md)
