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

## Live calls (opt-in — not in this demo build)

Live `--execute` with CALL-E SDK is **Rajput's task (R5)**. When implemented:

1. Set `CALLE_API_KEY` and `CALLE_BASE_URL=https://api.heycall-e.com`
2. Use explicit `--execute --confirm-recipient-opt-in`
3. See `skills/shop-voice-checkin/references/safety.md`

Running `client.py --live` prints a reminder and exits — demo stays no-call.

## Side effects

| Mode | Network | Phone call | Credits |
| --- | --- | --- | --- |
| Default demo | No | No | 0 |
| `--live` (future SDK) | Yes | Yes | Uses CALL-E |

## Files

| File | Purpose |
| --- | --- |
| `example_request.json` | Morning inventory demo request (masked phone) |
| `example_request_sales.json` | Evening sales demo request |
| `fixtures/` | Fictional transcripts and structured results, plus a full week of calls, edge cases, and golden summaries |
| `client.py` | Demo runner |
| `summarize.py` | Weekly business insights, computed from the ledger (AR2) |
| `demo_ledger.py` | Builds a SQLite ledger from fixtures — **stand-in for `store.py` (R4) and ingest (R6)** until they land |
| `SCHEMA.md` | The ledger contract both sides build against |
| `tests/` | 21 tests. No credentials, no network, no calls |

## Tests

```bash
pip install pytest jsonschema
pytest tests -q
python fixtures/validate_fixtures.py
```

Neither places a phone call.

## Cancellation

Recurring check-ins are owned by the host scheduler, not this app. To stop them,
see [`scheduling.md`](../../../skills/shop-voice-checkin/references/scheduling.md#cancellation).
Clearing `recipient_consented` alone does **not** stop calls — the scheduler
never reads it.

## Skill

Agent workflow: [`skills/shop-voice-checkin/`](../../skills/shop-voice-checkin/)

## Project plan

[`docs/projects/voice-shop-manager/PROJECT_PLAN.md`](../../../docs/projects/voice-shop-manager/PROJECT_PLAN.md)
