---
name: shop-voice-checkin
description: Place consent-based outbound CALL-E phone check-ins with informal African and Indian retailers to capture morning inventory and evening sales through natural voice conversation, then return structured shop data for a voice-first business manager workflow.
license: MIT
---

# Shop Voice Check-in

Use this skill when a **shop owner has opted in** to regular phone check-ins instead of entering data into an app. The agent calls, speaks in simple English or Pidgin-influenced English, asks about stock and sales, and returns **structured JSON** for a local shop ledger.

This skill is the voice layer of **Voice Shop Manager** — "your business manager, on the phone."

## When to use

- **Morning inventory check-in** — approximate stock levels, low items, supplier mentions
- **Evening sales recap** — approximate daily revenue, top sellers, restock spend
- Voice-first workflows for informal retailers in Nigeria, West Africa, or similar markets (India via English/Hindi task variants)

Pair with the runnable app at `apps/python/shop-voice-manager/` (relative to this submission repository root) to persist results in SQLite and generate weekly summaries.

## When not to use

- Cold-calling retailers who did not consent
- Loan offers, credit scoring conversations, or regulated financial advice on the call
- Replacing a POS, accounting system, or tax filing workflow
- Batch supplier procurement calls without explicit authorization per recipient
- Recurring schedules without a separate scheduler wrapper — see [`call-reminder`](../call-reminder/)

## Required fields

For each call, require:

- `shop_id` — stable identifier for the retailer
- `call_type` — `inventory` or `sales`
- `phone` — E.164 number of the **consenting shop owner**
- `region` — CALL-E region code, e.g. `NG` or `IN`
- `locale` — CALL-E locale, e.g. `en`
- `recipient_consented` — must be `true` for live calls

Optional:

- `currency` — `NGN`, `INR`, etc.
- `language_style` — `pidgin-english` or `english`
- `products_to_ask` — short list for morning check-ins
- `timezone` — IANA name for scheduling context

Ask for any missing required field. Do not infer phone, region, locale, or timezone from context.

## Core workflow

1. Read `references/safety.md` and confirm **recipient consent**.
2. Choose call type: inventory (morning) or sales (evening).
3. Build task text from `references/call-scripts-pidgin.md` or `references/call-scripts-english.md`.
4. Attach the matching result schema:
   - inventory → `references/result-schema-inventory.json`
   - sales → `references/result-schema-sales.json`
5. **Preview first** — inspect the planned task and schema without placing a call.
6. Live call — only with explicit user approval and `--execute`-style confirmation in the runnable app.
7. Pass structured results to the shop ledger app or host workflow.

Use this shape:

```text
consent check -> build task + schema -> preview -> live call -> structured result -> shop ledger
```

## Call task template (inventory)

```text
Call the shop owner for a short morning inventory check-in. Use simple English
with Nigerian Pidgin phrases where natural. Ask about: {{products_to_ask}}.
For each product, capture approximate quantity and unit. Ask what is running low.
Disclose you are an AI assistant for their shop manager service. Keep the call
under {{max_minutes}} minutes. Do not give financial advice.
```

## Call task template (sales)

```text
Call the shop owner for a short evening sales recap. Ask roughly how much they
sold today, what sold best, and whether they bought stock for the shop today.
Disclose you are an AI assistant for their shop manager service. Keep the call
under {{max_minutes}} minutes. Do not give financial advice.
```

## Idempotency

Use one idempotency key per shop, call type, and calendar day:

```text
shopvoice-{shop_id}-inventory-{YYYY-MM-DD}
shopvoice-{shop_id}-sales-{YYYY-MM-DD}
```

## Runnable app

The reference runner lives at `apps/python/shop-voice-manager/`. Default mode is preview (no network call). See the app README for live opt-in flags.

## Assets

- `assets/sample-shop-profile.json` — fictional masked shop profile
- `assets/example-request.template.json` — request shape for the Python app

## Output

After a completed inventory call, expect fields such as `check_in_completed`, `products[]`, and optional `owner_notes`.

After a completed sales call, expect `sales_day_completed`, `estimated_revenue`, `top_sellers[]`, and optional procurement fields.

Mask phone numbers in any user-facing summary.

## Scheduling recurring check-ins

This skill places **one call per invocation**. For daily morning and evening check-ins, wrap it with [`call-reminder`](../call-reminder/) or a host cron / Task Scheduler job. The scheduler owns recurrence; CALL-E places one call per run.

## Related project docs

Hackathon plan: `docs/projects/voice-shop-manager/PROJECT_PLAN.md`
