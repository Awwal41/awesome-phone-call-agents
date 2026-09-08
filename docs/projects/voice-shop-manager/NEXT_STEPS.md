# Voice Shop Manager — Phase 2 next steps

**Your business manager, on the phone** — after check-ins, help the owner restock by calling vendors and calling the owner back with status.

This document is the product workflow for Phase 2. Implementation tasks are tracked as GitHub issues `P1`–`P8` (see [PROJECT_PLAN.md](./PROJECT_PLAN.md)).

## Goal

Turn low-stock signals from inventory check-ins into a **consent-gated procurement loop**:

```text
Inventory (running low)
  → Ask owner: place order?
  → Capture / reuse vendor (name, goods, phone)
  → Call vendor with quantities
  → Call owner back with status / ETA
```

Also support **new-user onboarding**: first call collects shop profile into SQLite so later check-ins have context.

## Example conversation

1. Morning inventory finds fish and rice running low.
2. Agent: *"Fish and rice dey finish. You want me to place order?"*
3. Owner: *"Yes — call Mama Sikiru for the fish, two cooler boxes. For rice use the same man from last week."*
4. Agent saves or looks up vendors (Mama Sikiru → fish; rice vendor from directory).
5. Agent places outbound call to Mama Sikiru with the order.
6. Agent calls the owner back: *"I don place the fish order. She say e go reach you around 4pm."*

Later the owner can say only *"call Mama Sikiru for the fish"* because the directory already stores who she is and what she sells.

## Safety rules (non-negotiable)

- Preview / dry-run by default; live dials need explicit opt-in flags.
- Owner must say **yes** before any vendor call; never auto-order from low stock alone.
- Separate consent to contact each vendor and to receive status callbacks.
- E.164 phones only; never invent a vendor number.
- Mask phones in logs and summaries.
- No loans, credit scoring, bank-account collection, or financial advice on calls.
  Offline weekly insights may still help a bank *later*; that stays out of the voice path.
- Idempotency keys per call type so retries do not double-dial.
- Document how to cancel scheduled follow-ups.

## Issue map (Phase 2)

| # | Issue | Task | Owner label |
| --- | --- | --- | --- |
| P1 | [#33](https://github.com/Awwal41/awesome-phone-call-agents/issues/33) | Vendor directory schema in SQLite | **Done** — schema v2 + store helpers |
| P2 | [#34](https://github.com/Awwal41/awesome-phone-call-agents/issues/34) | Reorder offer after low-stock inventory | Todo → Aranwa |
| P3 | [#35](https://github.com/Awwal41/awesome-phone-call-agents/issues/35) | Capture and save vendor details | Todo → Aranwa |
| P4 | [#29](https://github.com/Awwal41/awesome-phone-call-agents/issues/29) | Outbound restock call to vendor | Todo → Aranwa |
| P5 | [#36](https://github.com/Awwal41/awesome-phone-call-agents/issues/36) | Status callback to shop owner | Todo → Aranwa |
| P6 | [#30](https://github.com/Awwal41/awesome-phone-call-agents/issues/30) | New-user onboarding → shop profile in DB | Todo → Aranwa |
| P7 | [#31](https://github.com/Awwal41/awesome-phone-call-agents/issues/31) | Fixtures + integration test for the chain | Todo → Aranwa |
| P8 | [#32](https://github.com/Awwal41/awesome-phone-call-agents/issues/32) | Safety + skill docs for multi-party calls | **Done** |

Suggested remaining order for Aranwa: **P2 + P3** → **P6** → **P4** → **P5** → **P7**.

**New goods:** Already supported — any product name spoken on an inventory call is upserted into `products` (see inventory scripts + `test_new_goods_mentioned_on_inventory_call_are_added`).

## Still open from Phase 1

| Issue | Task |
| --- | --- |
| [#15](https://github.com/Awwal41/awesome-phone-call-agents/issues/15) | R5 — live CALL-E SDK path (needed before live P4/P5) |
| [#21](https://github.com/Awwal41/awesome-phone-call-agents/issues/21) | AR5 — India locale |
| [#9](https://github.com/Awwal41/awesome-phone-call-agents/issues/9) | A9 — upstream PR |
| [#11](https://github.com/Awwal41/awesome-phone-call-agents/issues/11) | R1 — confirm schema (may close after P1 review) |

Filter: https://github.com/Awwal41/awesome-phone-call-agents/issues?q=label%3Avoice-shop-manager
