# Demo video script (2:55 — hard limit 3:00)

> **Timing is a submission rule, not a guideline.** The rules require under
> 3 minutes. This script is cut to **2:55**, leaving 5 seconds of margin.
> If a segment runs long while recording, cut from the closing line — never
> from the live call clip, which is the most persuasive 60 seconds in the film.

**Title:** Voice Shop Manager — Your business manager, on the phone  
**Audience:** Hackathon judges + Devpost  
**CALL-E account email:** _(add at submission)_

---

## 0:00–0:25 — Problem

**Visual:** Simple slide or talking head + market photo

> "Small retailers in Africa and India make sales every day — but money still leaks out. They buy from many suppliers, track nothing formally, and don't have time to enter data into apps. They know roughly what's in the shop, but not their real inventory, daily profit, or working capital."

**On screen:** Bullet list — no formal inventory · cash + WhatsApp purchases · revenue without capital growth

---

## 0:25–0:50 — Solution

**Visual:** Architecture diagram from PROJECT_PLAN.md

> "Voice Shop Manager flips the model. Instead of 'download an app and enter 150 products,' we say 'just talk to us.' CALL-E calls the shop owner in plain English or Pidgin, asks simple questions, and turns the conversation into structured business data."

**On screen:** Voice → CALL-E → JSON → SQLite → Weekly summary

---

## 0:50–1:35 — Preview mode (no call placed)

**Visual:** Terminal screen recording

```bash
cd apps/python/shop-voice-manager
python client.py --request example_request.json
```

> "Default mode is preview — no call, no credits used. You see the exact task, schema, and masked phone before anything goes live."

**On screen:** Highlight `preview`, fictional `+2348000000000`, inventory schema

---

## 1:35–2:35 — Live call clip (one real call) — do not cut

**Visual:** Waveform or call status UI + short transcript excerpt (with owner consent)

> "Good morning o. How market? How many bags of rice you get now? … About eight. Which thing don finish? … Indomie dey almost finish."

**On screen:** Structured JSON result populating after call completes

> "The agent adapts in real time. We don't need perfect accounting — approximate answers are enough to build a useful picture over time."

**Note:** Use one live CALL-E call for this segment. Mask phone number in video.

---

## 2:35–2:55 — Weekly summary + close

**Visual:** Terminal output from `summarize.py` (verbatim from the demo run)

```text
This week you sold about ₦425,000. You spent about ₦310,000 restocking.
Products running low: Indomie, Sugar.
Approximate capital in slow-moving stock: ₦45,000.
```

> "A week of calls, and the shop owner can see sales, restock spend, and the
> ₦45,000 sitting in stock that isn't moving — from conversations, not data
> entry. Inventory, sales, procurement, finance, advice. Nigeria today, India
> next."

**On screen:** End card with the three links below.

_One take, one breath — this is the 20 seconds most likely to overrun._

---

## Recording checklist

- [ ] Public YouTube or Vimeo link
- [ ] Mask real phone numbers
- [ ] Show CALL-E + awesome-phone-call-agents PR link at end
- [ ] **Under 3:00 total length** — check the export, not the script
- [ ] Consent obtained from anyone heard on the live call clip

## Links to show in end card

- GitHub PR: `https://github.com/CALLE-AI/awesome-phone-call-agents/pull/...`
- Project branch: `https://github.com/Awwal41/awesome-phone-call-agents/tree/feat/shop-voice-manager`
- CALL-E: `https://www.heycall-e.com/`
