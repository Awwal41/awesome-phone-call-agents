# Pull request body

Draft for the upstream PR into `CALLE-AI/awesome-phone-call-agents`.
Not part of the submission itself; see the note at the bottom about excluding
`docs/projects/` from the PR.

**Title**

```text
feat(apps): add shop-voice-checkin skill and shop-voice-manager app
```

---

## Summary

Voice Shop Manager gives small informal retailers a business record they will
never sit down and type.

Inventory software already exists for these shops. It does not get used,
because every one of those tools opens with "enter your 150 products", and an
owner running a counter alone will never do that. So the system phones them
instead, twice a day, in the English or Pidgin they already speak.

| Call | What it sounds like | What it produces |
| --- | --- | --- |
| Morning, inventory check-in | "Good morning o. How market? How many bags of rice you get now?" | Stock per product, what is running low, supplier mentions, last purchase price |
| Evening, sales recap | "How business today? Roughly how much you sell?" | Estimated revenue, top sellers, restock spend, supplier and amount |

The owner is allowed to be vague. "About eight." "Like ten carton." The result
schema is built for approximations, because the value is the trend over weeks,
not precision on any one day.

CALL-E returns the conversation already conforming to a JSON schema this repo
supplies, which is what turns a phone call into a database row. After roughly a
week of check-ins the app produces:

```text
This week you sold about ₦425,000. You spent about ₦310,000 restocking.
Products running low: Indomie, Sugar.
Approximate capital in slow-moving stock: ₦88,000.
```

**Why this is shaped differently from most entries here.** This repository
already contains many phone-call skills, and most are one-shot lookups:
`pharmacy-stock-check` rings around pharmacies for a medication;
`metapelet-elder-checkin` makes a single wellbeing call. Voice Shop Manager is
recurring state accumulation. Each call writes into a persistent per-shop
ledger, and the value compounds because the results build a record rather than
answering a question once.

## What is included

**`skills/shop-voice-checkin/`** — the portable Agent Skill: how any agent
should run these calls. Call scripts in English and Pidgin, result schemas for
inventory, sales and payment consent, safety and consent rules, a scheduling
reference with cancellation, and demo-mode instructions.

**`apps/python/shop-voice-manager/`** — the runnable app. Standard library
only; `dependencies = []` and a test asserts it stays that way.

| Piece | What it does |
| --- | --- |
| `client.py` | CLI. Preview by default, live call behind two explicit flags |
| `live_call.py` | The CALL-E path: trusted-host allowlist, consent check, crash-safe checkpoints |
| `ingest.py` | Turns a call result into ledger rows, confidence-gated and idempotent |
| `store.py` | SQLite ledger, six tables, documented in `SCHEMA.md` |
| `summarize.py` | Weekly plain-language summary computed from the ledger |
| `web/` | Operator console: shops, call history, live call status, transcripts |
| `fixtures/` | A full week of fictional calls plus five edge cases |
| `tests/` | 108 tests. No credentials, no network, no calls |

## Type

- [x] New skill
- [x] New runnable app
- [ ] New workflow plugin
- [ ] New provider adapter
- [ ] New scheduler recipe
- [x] README awesome-list entry
- [x] Safety or documentation update
- [ ] Validation or tooling update

## Side effects

Stated plainly because this software makes a phone ring.

| Mode | Network | Phone call | Credits |
| --- | --- | --- | --- |
| Default, `--fixture`, `--weekly-summary` | No | No | 0 |
| `pytest` | No | No | 0 |
| Web console, browsing | No | No | 0 |
| Web console with `SHOPVOICE_DEMO=1` | No | No | 0 |
| `--execute --confirm-recipient-opt-in` | Yes | **Yes** | 1 per call |
| Web console, Place check-in call | Yes | **Yes** | 1 per call |

**No call happens without two deliberate acts.** `recipient_consented` must be
true in the request, and `--confirm-recipient-opt-in` must be passed. The
console records consent when a shop is added, then confirms the cost at dial
time rather than asking for consent again.

**One call per shop per call type per day.** The idempotency key is
`shopvoice-{shop_id}-{call_type}-{date}`, and a checkpoint under
`.call-state/` records the call id the moment CALL-E returns one, so a crash
mid-call or a rerun **polls the existing call instead of placing a second**.
A repeat is possible but must be asked for, and its key stays derived rather
than random: a random key would give a rerun a fresh checkpoint path, find no
call id, and dial again. Checkpoints store a masked phone and a hash, never the
full number.

**Cancellation.** Recurring check-ins are owned by the host scheduler, not this
app. `skills/shop-voice-checkin/references/scheduling.md#cancellation` covers
removing them. Clearing `recipient_consented` alone does **not** stop calls,
because the scheduler never reads it, and the docs say so.

## AI disclosure

Both call task templates instruct the agent to disclose that the caller is an
AI, and both script references carry a required disclosure line, including the
Pidgin one:

> "I be AI assistant wey dey help you track your shop. This call fit dey recorded."

This is deliberate. Nothing in the base CLI, the bundled skills, or
`call-e-safety.mdc` currently requires disclosing to the callee that they are
speaking to an AI; the existing safety guidance protects the operator. The
person who did not choose to be part of this is the one who picks up the phone,
so the skill discloses to them.

## Verification

```bash
python3 scripts/validate_repository.py     # Repository validation passed
./check.sh                                  # validation + fixtures + 108 tests
```

`tests/test_no_live_calls.py` scans every test file for anything that could
dial, and asserts the app declares no dependencies. Naming the CALL-E host in a
test requires an explicit `# allow-host-literal` marker, so the exception stays
visible to a reviewer instead of quietly widening.

The pipeline has also been run end to end against the live API. One real call
completed on 7 Sep 2026 and was ingested through the same path the fixtures
use, so the demo cannot drift from production: there is one write path, and the
demo uses it. Call ids are recorded in `apps/python/shop-voice-manager/CALLS.md`,
generated from the local checkpoints with phone numbers and the account hash
deliberately excluded.

## Checklist

- [x] Repository-facing content is written in English.
- [x] Branch name, commit messages, and PR title follow `docs/git-naming-conventions.md`.
- [x] No secrets, tokens, private phone numbers, call recordings, or private transcripts are included.
- [x] Real-world side effects are clearly described.
- [x] Phone numbers are masked in documentation and test fixtures unless they are clearly fictional.
- [x] Recurring workflows include cancellation behavior.
- [x] Runnable code has a dry-run, fake-server, or no-call path by default.
- [x] `python3 scripts/validate_repository.py` passes.

Every number in the diff is fictional or from a reserved range
(`+2348000000000`, `+919000000000`, `+447700900000`). The transcript of the one
real call is not committed; raw call results are gitignored.

## Supported regions

The app carries no assumption about where a shop is. Country, currency,
language and speaking style are per shop, and the country supplies the defaults
it implies. Nigeria and India are the two markets the scripts and fixtures
cover today.

One note for the maintainers: outbound calls to Nigeria in English are
currently refused by the API with *"Calls to Nigeria in English aren't
supported for this product"*, although `NG` is listed as supported in the
integrations README region table. The app surfaces the refusal rather than
pre-blocking it, so if the account gate changes nothing needs to be edited.

---

## Note before opening

Exclude `docs/projects/voice-shop-manager/` from the upstream PR. Those eight
files are internal planning: the project plan, Devpost checklist, demo script,
walkthrough, next steps, and this file. They are useful to us and noise to a
reviewer, and `DEVPOST_CHECKLIST.md` in particular does not belong in someone
else's repository.

Everything else in the diff is the submission: 81 files, of which 14 are the
skill and the rest the app, its fixtures and its tests.
