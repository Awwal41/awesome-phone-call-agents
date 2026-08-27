do# Demo walkthrough (no live call)

Record your hackathon video from these steps, or run them live for judges.

## Prerequisites

- Python 3.11+
- Clone `feat/shop-voice-manager` from `Awwal41/awesome-phone-call-agents`

## Step 1 — Problem (30s)

Read from [`DEMO_SCRIPT.md`](./DEMO_SCRIPT.md) opening: informal retailers lose working capital without formal inventory tools.

## Step 2 — Morning check-in preview (45s)

```bash
cd apps/python/shop-voice-manager
python client.py --request example_request.json
```

Show on screen:

- `"mode": "demo"` and `"side_effects": "none"`
- Pidgin-influenced task text
- Inventory result schema attached
- Fixture structured result (8 bags rice, Indomie running low)

Optional: open `fixtures/demo-transcript-inventory.txt` as the “call clip” instead of a live recording.

## Step 3 — Evening sales demo (30s)

```bash
python client.py --request example_request_sales.json
```

Show estimated revenue ₦85,000 and procurement spend in fixture JSON.

## Step 4 — Weekly summary (30s)

```bash
python client.py --request example_request.json --weekly-summary
```

Show terminal summary: sales vs restock, low stock, capital tied in slow movers.

## Step 5 — Vision (15s)

Five agents: Inventory · Sales · Procurement · Finance · Advisor — all via voice.

Point to [`PROJECT_PLAN.md`](./PROJECT_PLAN.md) architecture diagram.

## Optional live CALL-E segment

If you have CALL-E auth and credits, add a **short** live clip after the demo sections. Not required for this demo submission — fixtures are the default proof.

See [`CALLE_SETUP.md`](./CALLE_SETUP.md).

## What to upload

- YouTube/Vimeo public link (~3 min)
- Paste PR URL into Devpost ([`DEVPOST_CHECKLIST.md`](./DEVPOST_CHECKLIST.md))
