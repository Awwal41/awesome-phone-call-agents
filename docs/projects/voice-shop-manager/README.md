# Voice Shop Manager

**Your business manager, on the phone.**

## Demo status

**Done** — run without CALL-E auth or live calls:

```bash
cd apps/python/shop-voice-manager
python client.py --request example_request.json --weekly-summary
python client.py --request example_request_inr.json   # India / INR
```

Phase 2 procurement + Phase 3 payouts ship as fixtures and tests (no live dials by default). See **[NEXT_STEPS.md](./NEXT_STEPS.md)**.

```text
Low stock → ask to place order → save vendors → call vendors → call owner back
```

## Team

| Person | Status |
| --- | --- |
| **Awwal** | Demo + safety + Phase 3 payout foundation + upstream PR |
| **Aranwa** | Insights, tests, docs, India locale, Phase 2 procurement |
| **Rajput** | App scaffold, SQLite ledger, ingest |

**Plan:** [PROJECT_PLAN.md](./PROJECT_PLAN.md) · **Next steps:** [NEXT_STEPS.md](./NEXT_STEPS.md) · **Walkthrough:** [DEMO_WALKTHROUGH.md](./DEMO_WALKTHROUGH.md)

**Issues:** https://github.com/Awwal41/awesome-phone-call-agents/issues?q=label%3Avoice-shop-manager
