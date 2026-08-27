# Voice Shop Manager (Python demo)

**Your business manager, on the phone** — demo build for the CALL-E hackathon.

Voice-first check-ins for informal retailers: morning inventory and evening sales captured by CALL-E, structured into JSON, summarized into weekly business insights.

> **Demo mode:** This app runs **without** a live phone call or API key by default. Fixtures simulate completed calls so judges and collaborators can run the flow locally.

## Quick start (demo — no CALL-E credits)

```bash
cd apps/python/shop-voice-manager
python client.py --request example_request.json
python client.py --request example_request_sales.json
python client.py --request example_request.json --weekly-summary
```

Expected: masked preview plan + fixture structured result. No network.

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
| `fixtures/` | Fictional transcripts and structured results |
| `client.py` | Demo runner |

## Skill

Agent workflow: [`skills/shop-voice-checkin/`](../../skills/shop-voice-checkin/)

## Project plan

[`docs/projects/voice-shop-manager/PROJECT_PLAN.md`](../../../docs/projects/voice-shop-manager/PROJECT_PLAN.md)
