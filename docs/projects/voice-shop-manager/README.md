# Voice Shop Manager

**Your business manager, on the phone.**

AI check-in calls for informal African (and Indian) retailers — inventory and sales captured by voice, structured into a shop ledger, summarized into weekly business insights.

## Team

| Person | Focus |
| --- | --- |
| **Awwal** | Product, CALL-E setup, skill + call scripts, demo video, Devpost, upstream PR |
| **Rajput** | Python app core — scaffold, SQLite store, SDK integration, result ingest |
| **Aranwa** | Weekly insights, tests, docs, scheduler, India locale, CLI output, validation |

## Start here

Full plan: **[PROJECT_PLAN.md](./PROJECT_PLAN.md)**

## Rajput — your tasks (R1–R6)

1. Clone `https://github.com/Awwal41/awesome-phone-call-agents.git`
2. Checkout branch `feat/shop-voice-manager`
3. Build app core: `apps/python/shop-voice-manager/` (scaffold, store, SDK, ingest)
4. Pair with Aranwa on S2 (integration test)

## Aranwa — your tasks (AR1–AR8)

1. Clone fork, checkout `feat/shop-voice-manager`
2. Build `summarize.py`, tests, fixtures, scheduler doc, app README
3. India locale: Hindi-English scripts + INR shop profile (AR5)
4. Run validation before PR (AR8)

## Awwal — your tasks (A1–A10)

1. Finish CALL-E auth (`npx -y @call-e/cli auth login`)
2. Build `skills/shop-voice-checkin/`
3. Record demo + submit Devpost
