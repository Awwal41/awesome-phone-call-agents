# Safety — shop voice check-in calls

## Intent and consent

- Place an outbound call only when the **shop owner has explicitly agreed** to regular business check-ins from this service.
- Do not cold-call retailers, suppliers, or customers for lead generation.
- Default runnable app mode is **preview** (no CALL-E network call).

## Non-financial boundaries

This skill collects **operational shop data**, not regulated financial advice.

- No loan offers, credit decisions, insurance sales, or investment advice on the call.
- No promises about profit, savings, or business outcomes.
- If the owner asks for formal accounting or tax help, suggest they speak with a qualified human professional.
- No emergency handling — the agent is not a security or medical service.
- No bank-account collection or credit scoring on any call. Offline weekly insights may later inform a bank conversation; that stays out of the voice path.

## Phone numbers and data

- Use **E.164** format for live runs.
- Set explicit CALL-E **region** and **locale** in the request — do not infer routing from the number prefix.
- Mask phone numbers in logs, previews, demo video, and git.
- Do not commit API keys, live request files, or call results with full transcripts.
- Never invent a vendor or owner phone number. Leave vendor `phone_e164` null until the owner provides it.

## Side effects

- Live execution creates a **real phone call** and consumes CALL-E credits.
- One shop owner per call task unless the user explicitly authorizes batch outreach.
- Morning inventory and evening sales are **separate call tasks** with separate idempotency keys.

## New goods on inventory calls

- Owners may introduce products that were not in the prior inventory list.
- Capture each new name with quantity and unit; the ledger upserts a new `products` row automatically.
- Do not refuse unknown product names. Do not require a pre-registered catalog.

## Phase 2 — multi-party procurement (owner ↔ agent ↔ vendor)

When restock workflows are enabled (issues P2–P5):

1. **Owner must say yes** before any vendor is contacted. Low stock alone never auto-orders.
2. **Per-vendor authorization** — the owner must authorize contacting that specific vendor (or confirm a saved vendor by name).
3. **Separate consent for status callbacks** — calling the owner back with ETA/status needs explicit opt-in (can be part of the restock yes).
4. **Preview by default** — live vendor dials and owner callbacks require the same dual flags as owner check-ins (`--execute --confirm-recipient-opt-in`) plus request-level consent fields.
5. **No recurring auto-orders** — each restock request is one-shot unless the host scheduler creates a new confirmed job with a cancel path.
6. Vendor and callback calls are **separate** from inventory/sales check-ins; do not combine them into one CALL-E task.

## Idempotency

Derive keys from shop identity and call type, not from retry attempt number:

```text
shopvoice-{shop_id}-inventory-{YYYY-MM-DD}
shopvoice-{shop_id}-sales-{YYYY-MM-DD}
shopvoice-{shop_id}-vendor_order-{request_id}
shopvoice-{shop_id}-order_status-{request_id}
shopvoice-{shop_id}-onboarding-{YYYY-MM-DD}
```

Do not place a duplicate live call for the same key unless the user explicitly requests a retry after a failed attempt.

## Cancellation

- Before execution: use preview mode; omit live flags.
- For recurring check-ins scheduled via a host cron or Task Scheduler: deleting or disabling that job stops future calls. Clearing `recipient_consented` alone does **not** — the scheduler never reads it. See [`scheduling.md`](./scheduling.md#cancellation).
- Cancel a draft restock request by setting status to `cancelled` before a vendor dial; document the cancel path in the scheduler recipe when Phase 2 goes live.
- After CALL-E accepts a task, use dashboard controls if cancel is available before the dial completes.

## Platform coverage

Confirm outbound regions and locales against CALL-E [supported regions and languages](https://github.com/CALLE-AI/call-e-integrations#-supported-regions-and-languages) before live runs. Nigeria (`NG`) and India (`IN`) are supported for hackathon pilots.

## Privacy

- Structured results may include approximate revenue and supplier names — treat as business-confidential.
- Share summaries only with the authorized shop owner or their designated operator.
- Do not reuse one retailer's data to advise another without explicit aggregation and consent (post-MVP).
