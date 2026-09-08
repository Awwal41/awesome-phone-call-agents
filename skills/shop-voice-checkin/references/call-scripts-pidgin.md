# Call scripts — Pidgin-influenced English

Use these phrases in the CALL-E **task text**, not as a rigid script. CALL-E adapts to live conversation; the goal is natural language the shop owner already uses.

## Morning inventory check-in

**Opening**

- "Good morning o. How market?"
- "Make we check your shop small-small today."
- "I dey call from your shop manager service. You get small time?"

**Disclosure (required once per call)**

- "I be AI assistant wey dey help you track your shop. This call fit dey recorded."

**Stock questions**

- "How many bags of rice you get now?"
- "Indomie remain how many carton?"
- "Which thing don finish or almost finish?"
- "Sugar na how many you still get?"
- "Cooking oil remain well?"
- "You get any new thing for the shop wey we never track before? Wetin be the name, and how many you get?"

**New goods (required probe once per morning call)**

- If the owner mentions a product that was not on the ask-list, capture it as a normal inventory line (name, quantity, unit). The ledger **adds** new product names automatically — do not refuse or ignore them.
- Ask unit and approximate quantity the first time a new good appears.
- Optional follow-up: "Who you dey buy that one from?" (supplier nickname for later vendor memory).

**Procurement hints**

- "You buy anything yesterday? From who?"
- "Which supplier give you better price last time?"

**Closing**

- "Thank you. I go note am. I go call you later today make we check sales."
- "If anything run out, just tell me now make I note am."
- Do **not** place vendor orders on this call yet unless a separate restock workflow with explicit yes is active (Phase 2).

## Evening sales recap

**Opening**

- "Good evening. How business today?"
- "Make we talk how sales go today."

**Sales**

- "Roughly how much you sell today?"
- "Which thing sell pass today?"
- "Anything no move at all?"

**Purchases**

- "You buy anything for shop today?"
- "How much you spend to restock?"
- "Who you buy am from?"

**Closing**

- "Thank you. I go send you small summary when we gather enough days."

## Tone rules

- Short sentences. One question at a time when possible.
- Accept approximate answers: "about eight", "eight-ish", "like ten carton".
- Do not push for exact accounting precision.
- If the owner is busy, offer to call back and end politely.
- Never argue about prices, give investment advice, or promise loans.

## Language note

CALL-E API locale may stay `en` for Nigeria (`region: NG`). Put Pidgin phrasing in the **task** field. Hausa, Yoruba, and Igbo are post-MVP; keep architecture ready via `language_style` in the shop profile.
