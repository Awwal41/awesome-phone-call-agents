# Ledger schema contract

Agreed shape of the SQLite ledger. `store.py` (#14) owns creating and writing
these tables. `summarize.py` (#18) only reads them.

Refs #14, #18.

## Two additions to the plan

`PROJECT_PLAN.md` specifies four tables. Two more are required, because the
weekly summary cannot be computed without them:

| Table | Why it is needed |
| --- | --- |
| `inventory_readings` | `products` is keyed `(shop_id, name_normalized)`, so it holds only the **latest** quantity. Detecting whether stock moved over a week needs the reading from each day. |
| `procurement_items` | `daily_sales.procurement_spend` is a lump total. Attributing restocking to a product needs the line items. |

`products` stays exactly as planned and remains the fast latest-state lookup.

## Tables

```sql
CREATE TABLE shops (
  id            TEXT PRIMARY KEY,
  display_name  TEXT,
  phone_e164    TEXT NOT NULL,
  region        TEXT NOT NULL,
  locale        TEXT NOT NULL,
  currency      TEXT DEFAULT 'NGN',
  created_at    TEXT NOT NULL
);

CREATE TABLE products (
  shop_id            TEXT NOT NULL,
  name_normalized    TEXT NOT NULL,
  display_name       TEXT NOT NULL,
  quantity_estimate  REAL,
  unit               TEXT,
  running_low        INTEGER DEFAULT 0,
  preferred_supplier TEXT,
  last_cost          REAL,
  updated_at         TEXT NOT NULL,
  PRIMARY KEY (shop_id, name_normalized)
);

CREATE TABLE inventory_readings (
  shop_id           TEXT NOT NULL,
  reading_date      TEXT NOT NULL,
  name_normalized   TEXT NOT NULL,
  display_name      TEXT NOT NULL,
  quantity_estimate REAL,
  unit              TEXT,
  running_low       INTEGER DEFAULT 0,
  source_call_id    TEXT,
  PRIMARY KEY (shop_id, reading_date, name_normalized)
);

CREATE TABLE daily_sales (
  shop_id            TEXT NOT NULL,
  sales_date         TEXT NOT NULL,
  estimated_revenue  REAL,
  procurement_spend  REAL,
  top_sellers_json   TEXT,
  source_call_id     TEXT,
  PRIMARY KEY (shop_id, sales_date)
);

CREATE TABLE procurement_items (
  shop_id         TEXT NOT NULL,
  purchase_date   TEXT NOT NULL,
  name_normalized TEXT NOT NULL,
  display_name    TEXT NOT NULL,
  amount          REAL,
  supplier        TEXT,
  source_call_id  TEXT,
  PRIMARY KEY (shop_id, purchase_date, name_normalized)
);

CREATE TABLE call_receipts (
  call_id        TEXT PRIMARY KEY,
  shop_id        TEXT NOT NULL,
  call_type      TEXT NOT NULL,
  status         TEXT NOT NULL,
  task_completed INTEGER,
  confidence     REAL,
  created_at     TEXT NOT NULL
);
```

`call_receipts.confidence` is added so a rejected low-confidence call still
leaves an audit trail explaining why nothing was written.

## Ingest rules that the summary depends on

1. **Write a receipt for every call**, including failures. The receipt is the
   record that a call happened; the other tables are the record of what it said.
2. **Gate on confidence, not on `task_completed`.** A result may report
   `task_completed: true` and still be unreliable — see
   `fixtures/edge-cases/low-confidence.json`. Below the threshold, write the
   receipt only.
3. **Never zero out a product that was not discussed.** A partial check-in
   updates the products it covered and leaves the rest untouched.
4. **Populate `products.last_cost`.** Prefer `last_purchase_price` from the call
   result; otherwise seed from the shop profile's `reference_cost`. Without it,
   quantities cannot be converted to money and the capital figure is skipped.
5. **Normalize names by lowercasing and trimming.** `name_normalized` is the
   join key; `display_name` is what the owner said.

## Dates

`reading_date`, `sales_date`, and `purchase_date` are `YYYY-MM-DD` in the shop's
local timezone, taken from the call's `metadata.call_date`.
