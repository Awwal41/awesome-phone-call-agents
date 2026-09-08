# Voice Shop Manager

**Your business manager, on the phone.**

## Demo status

**Awwal tasks: Done (demo)** — run without CALL-E auth or live calls:

```bash
cd apps/python/shop-voice-manager
python client.py --request example_request.json --weekly-summary
```

## Next steps (Phase 2)

Procurement loop + new-user onboarding — see **[NEXT_STEPS.md](./NEXT_STEPS.md)**.

```text
Low stock → ask to place order → save vendors → call vendors → call owner back
```

**Done locally:** P1 (vendor schema) · P8 (safety docs) · new-goods probe on inventory calls · Phase 3 P9–P12 payout foundation  
**Assigned to Aranwa:** P2–P7 plus remaining open Phase 1 items (leave Phase 3 payment hooks — see NEXT_STEPS)

## Phase 3 (vendor payouts)

Owner pay-yes → payment intent → fake adapter. Issues [#37](https://github.com/Awwal41/awesome-phone-call-agents/issues/37)–[#40](https://github.com/Awwal41/awesome-phone-call-agents/issues/40) (Awwal). Details in [NEXT_STEPS.md](./NEXT_STEPS.md).

## Team

| Person | Status |
| --- | --- |
| **Awwal** | Demo + P1/P8 + Phase 3 payout foundation |
| **Aranwa** | Owns remaining Phase 2 (P2–P7) and open follow-ups |
| **Rajput** | Prior app/SDK work; Phase 2 dials handed to Aranwa |

**Plan:** [PROJECT_PLAN.md](./PROJECT_PLAN.md) · **Next steps:** [NEXT_STEPS.md](./NEXT_STEPS.md) · **Walkthrough:** [DEMO_WALKTHROUGH.md](./DEMO_WALKTHROUGH.md)

**Issues:** https://github.com/Awwal41/awesome-phone-call-agents/issues?q=label%3Avoice-shop-manager
