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

## Phone numbers and data

- Use **E.164** format for live runs.
- Set explicit CALL-E **region** and **locale** in the request — do not infer routing from the number prefix.
- Mask phone numbers in logs, previews, demo video, and git.
- Do not commit API keys, live request files, or call results with full transcripts.

## Side effects

- Live execution creates a **real phone call** and consumes CALL-E credits.
- One shop owner per call task unless the user explicitly authorizes batch outreach.
- Morning inventory and evening sales are **separate call tasks** with separate idempotency keys.

## Idempotency

Derive keys from shop identity and call type, not from retry attempt number:

```text
shopvoice-{shop_id}-inventory-{YYYY-MM-DD}
shopvoice-{shop_id}-sales-{YYYY-MM-DD}
```

Do not place a duplicate live call for the same shop, call type, and calendar day unless the user explicitly requests a retry after a failed attempt.

## Cancellation

- Before execution: use preview mode; omit live flags.
- For recurring check-ins scheduled via a host cron or Task Scheduler: deleting or disabling that job stops future calls.
- After CALL-E accepts a task, use dashboard controls if cancel is available before the dial completes.

## Platform coverage

Confirm outbound regions and locales against CALL-E [supported regions and languages](https://github.com/CALLE-AI/call-e-integrations#-supported-regions-and-languages) before live runs. Nigeria (`NG`) and India (`IN`) are supported for hackathon pilots.

## Privacy

- Structured results may include approximate revenue and supplier names — treat as business-confidential.
- Share summaries only with the authorized shop owner or their designated operator.
- Do not reuse one retailer's data to advise another without explicit aggregation and consent (post-MVP).
