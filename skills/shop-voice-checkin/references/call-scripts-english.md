# Call scripts — plain English

Use when the shop owner prefers standard English, or for India pilots (`region: IN`).

## Morning inventory check-in

**Opening**

- "Good morning. Can we do a quick shop check-in?"
- "I'm calling from your shop manager service. Do you have a few minutes?"

**Disclosure**

- "I'm an AI assistant helping track your shop. This call may be recorded."

**Stock questions**

- "How many bags of rice do you have now?"
- "How many cartons of noodles are left?"
- "What is running low or almost finished?"
- "How much sugar is left?"
- "Do you still have enough cooking oil?"
- "Did you add any new goods we have not tracked before? What are they called, and roughly how many do you have?"

**New goods (probe once per morning call)**

- If the owner names a product that was not on the ask-list, capture it as a normal inventory line (name, quantity, unit). The ledger **adds** new product names automatically — do not refuse or ignore them.
- Ask unit and approximate quantity the first time a new good appears.
- Optional: "Who do you usually buy that from?" (for later vendor memory).

**Procurement hints**

- "Did you buy anything yesterday? From whom?"
- "Which supplier gave you a better price recently?"

**Closing**

- "Thank you. I'll note this and call later to check today's sales."
- Do **not** place vendor orders on this call yet unless a separate restock workflow with explicit yes is active (Phase 2).

## Evening sales recap

**Opening**

- "Good evening. How was business today?"

**Sales**

- "Roughly how much did you sell today?"
- "What sold best today?"
- "Did anything not move at all?"

**Purchases**

- "Did you buy anything for the shop today?"
- "About how much did you spend restocking?"
- "Who did you buy from?"

**Closing**

- "Thank you. I'll share a short summary once we have a few days of data."

## India variant notes

- Use `region: IN` and `locale: en` or `hi` per CALL-E supported languages.
- Currency in results: `INR`.
- Aranwa maintains a Hindi-English script variant separately (`AR5`).

## Tone rules

Same as Pidgin scripts: accept approximations, one question at a time, no financial advice.
