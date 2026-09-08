#!/usr/bin/env python3
"""SQLite ledger for Voice Shop Manager.

Owns the schema and the write primitives. It holds no policy about which calls
are worth recording — that belongs in `ingest.py`, because policy changes far
more often than schema does.

    python3 store.py --init shop.db

Schema contract: SCHEMA.md. Refs #14, #33 (P1 vendors).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shops (
  id TEXT PRIMARY KEY, display_name TEXT, phone_e164 TEXT NOT NULL,
  region TEXT NOT NULL, locale TEXT NOT NULL, currency TEXT DEFAULT 'NGN',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
  shop_id TEXT NOT NULL, name_normalized TEXT NOT NULL, display_name TEXT NOT NULL,
  quantity_estimate REAL, unit TEXT, running_low INTEGER DEFAULT 0,
  preferred_supplier TEXT, last_cost REAL, updated_at TEXT NOT NULL,
  PRIMARY KEY (shop_id, name_normalized)
);
CREATE TABLE IF NOT EXISTS inventory_readings (
  shop_id TEXT NOT NULL, reading_date TEXT NOT NULL, name_normalized TEXT NOT NULL,
  display_name TEXT NOT NULL, quantity_estimate REAL, unit TEXT,
  running_low INTEGER DEFAULT 0, source_call_id TEXT,
  PRIMARY KEY (shop_id, reading_date, name_normalized)
);
CREATE TABLE IF NOT EXISTS daily_sales (
  shop_id TEXT NOT NULL, sales_date TEXT NOT NULL, estimated_revenue REAL,
  procurement_spend REAL, top_sellers_json TEXT, source_call_id TEXT,
  PRIMARY KEY (shop_id, sales_date)
);
CREATE TABLE IF NOT EXISTS procurement_items (
  shop_id TEXT NOT NULL, purchase_date TEXT NOT NULL, name_normalized TEXT NOT NULL,
  display_name TEXT NOT NULL, amount REAL, supplier TEXT, source_call_id TEXT,
  PRIMARY KEY (shop_id, purchase_date, name_normalized)
);
CREATE TABLE IF NOT EXISTS call_receipts (
  call_id TEXT PRIMARY KEY, shop_id TEXT NOT NULL, call_type TEXT NOT NULL,
  status TEXT NOT NULL, task_completed INTEGER, confidence REAL,
  accepted INTEGER NOT NULL DEFAULT 0, reason TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vendors (
  vendor_id TEXT PRIMARY KEY,
  shop_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  name_normalized TEXT NOT NULL,
  phone_e164 TEXT,
  goods_json TEXT NOT NULL DEFAULT '[]',
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (shop_id, name_normalized)
);
CREATE TABLE IF NOT EXISTS restock_requests (
  request_id TEXT PRIMARY KEY,
  shop_id TEXT NOT NULL,
  status TEXT NOT NULL,
  items_json TEXT NOT NULL,
  owner_consented INTEGER NOT NULL DEFAULT 0,
  source_call_id TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL,
  shop_id TEXT NOT NULL,
  vendor_id TEXT NOT NULL,
  status TEXT NOT NULL,
  eta_text TEXT,
  amount REAL,
  vendor_call_id TEXT,
  callback_call_id TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_readings_shop_date ON inventory_readings(shop_id, reading_date);
CREATE INDEX IF NOT EXISTS idx_sales_shop_date ON daily_sales(shop_id, sales_date);
CREATE INDEX IF NOT EXISTS idx_receipts_shop ON call_receipts(shop_id, created_at);
CREATE INDEX IF NOT EXISTS idx_vendors_shop ON vendors(shop_id, name_normalized);
CREATE INDEX IF NOT EXISTS idx_restock_shop ON restock_requests(shop_id, created_at);
CREATE INDEX IF NOT EXISTS idx_orders_shop ON orders(shop_id, created_at);
"""


class StoreError(Exception):
    pass


def normalize(name: str) -> str:
    """Join key for a product. Display name is kept separately, as spoken."""
    return " ".join(str(name).strip().lower().split())


def connect(path: Path | str, read_only: bool = False) -> sqlite3.Connection:
    path = Path(path)
    if read_only:
        if not path.is_file():
            raise StoreError(f"No ledger at {path}")
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    """Create the schema if absent. Safe to call on an existing ledger.

    Version 1 ledgers are upgraded in place: Phase 2 tables are added with
    ``CREATE TABLE IF NOT EXISTS`` and the meta version is bumped to 2.
    """
    with conn:
        conn.executescript(SCHEMA)
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO schema_meta (key, value) VALUES ('version', ?)",
                (str(SCHEMA_VERSION),),
            )
        elif int(row["value"]) == 1:
            # v1 → v2: new tables already created above; only the stamp changes.
            conn.execute(
                "UPDATE schema_meta SET value = ? WHERE key = 'version'",
                (str(SCHEMA_VERSION),),
            )


def schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM schema_meta WHERE key = 'version'").fetchone()
    return int(row["value"]) if row else 0


def check_compatible(conn: sqlite3.Connection) -> None:
    found = schema_version(conn)
    if found == 1:
        initialize(conn)
        found = schema_version(conn)
    if found != SCHEMA_VERSION:
        raise StoreError(
            f"Ledger is schema version {found}, this code expects {SCHEMA_VERSION}. "
            "Rebuild the ledger or add a migration."
        )


def mask_phone(phone: str | None) -> str:
    """Mask an E.164 number for logs and summaries. Never invent digits."""
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) < 4:
        return "***"
    return f"+{'*' * (len(digits) - 4)}{digits[-4:]}"


def _vendor_id(shop_id: str, name_normalized: str) -> str:
    return f"vendor-{shop_id}-{name_normalized.replace(' ', '-')}"


# ------------------------------------------------------------------ writes

def upsert_shop(conn: sqlite3.Connection, profile: dict) -> None:
    conn.execute(
        "INSERT INTO shops (id, display_name, phone_e164, region, locale, currency, created_at)"
        " VALUES (:id, :display_name, :phone, :region, :locale, :currency, :created_at)"
        " ON CONFLICT(id) DO UPDATE SET"
        "   display_name = excluded.display_name, phone_e164 = excluded.phone_e164,"
        "   region = excluded.region, locale = excluded.locale, currency = excluded.currency",
        {
            "id": profile["shop_id"],
            "display_name": profile.get("display_name"),
            "phone": profile["phone"],
            "region": profile["region"],
            "locale": profile["locale"],
            "currency": profile.get("currency", "NGN"),
            "created_at": profile.get("consent_timestamp", ""),
        },
    )


def seed_products(conn: sqlite3.Connection, profile: dict) -> None:
    """Seed known products and their reference costs.

    Without a cost the summary cannot convert quantities into money, and the
    call result only carries a price when the owner happens to mention one.
    """
    for product in profile.get("typical_products", []):
        conn.execute(
            "INSERT INTO products (shop_id, name_normalized, display_name, unit, last_cost, updated_at)"
            " VALUES (?, ?, ?, ?, ?, '')"
            " ON CONFLICT(shop_id, name_normalized) DO UPDATE SET"
            "   unit = COALESCE(products.unit, excluded.unit),"
            "   last_cost = COALESCE(products.last_cost, excluded.last_cost)",
            (
                profile["shop_id"], normalize(product["name"]), product["name"],
                product.get("unit"), product.get("reference_cost"),
            ),
        )


def record_receipt(conn: sqlite3.Connection, *, call_id: str, shop_id: str, call_type: str,
                   status: str, task_completed: bool, confidence: float | None,
                   accepted: bool, reason: str, created_at: str) -> None:
    conn.execute(
        "INSERT INTO call_receipts"
        " (call_id, shop_id, call_type, status, task_completed, confidence, accepted, reason, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(call_id) DO UPDATE SET"
        "   status = excluded.status, task_completed = excluded.task_completed,"
        "   confidence = excluded.confidence, accepted = excluded.accepted, reason = excluded.reason",
        (call_id, shop_id, call_type, status, 1 if task_completed else 0,
         confidence, 1 if accepted else 0, reason, created_at),
    )


def write_inventory_reading(conn: sqlite3.Connection, *, shop_id: str, reading_date: str,
                            product: dict, source_call_id: str) -> None:
    key = normalize(product["name"])
    conn.execute(
        "INSERT OR REPLACE INTO inventory_readings"
        " (shop_id, reading_date, name_normalized, display_name, quantity_estimate,"
        "  unit, running_low, source_call_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (shop_id, reading_date, key, product["name"], product.get("quantity_estimate"),
         product.get("unit"), 1 if product.get("running_low") else 0, source_call_id),
    )
    # Latest-state projection. COALESCE keeps a known value when this call did
    # not mention one — a partial check-in must not erase what we already knew.
    conn.execute(
        "INSERT INTO products (shop_id, name_normalized, display_name, quantity_estimate,"
        " unit, running_low, preferred_supplier, last_cost, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(shop_id, name_normalized) DO UPDATE SET"
        "   quantity_estimate = excluded.quantity_estimate,"
        "   unit = COALESCE(excluded.unit, products.unit),"
        "   running_low = excluded.running_low,"
        "   preferred_supplier = COALESCE(excluded.preferred_supplier, products.preferred_supplier),"
        "   last_cost = COALESCE(excluded.last_cost, products.last_cost),"
        "   updated_at = excluded.updated_at",
        (shop_id, key, product["name"], product.get("quantity_estimate"),
         product.get("unit"), 1 if product.get("running_low") else 0,
         product.get("supplier_mentioned"), product.get("last_purchase_price"), reading_date),
    )


def write_daily_sales(conn: sqlite3.Connection, *, shop_id: str, sales_date: str,
                      result: dict, source_call_id: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO daily_sales"
        " (shop_id, sales_date, estimated_revenue, procurement_spend, top_sellers_json, source_call_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (shop_id, sales_date, result.get("estimated_revenue"),
         result.get("procurement_spend") or 0,
         json.dumps(result.get("top_sellers", [])), source_call_id),
    )


def write_procurement_items(conn: sqlite3.Connection, *, shop_id: str, purchase_date: str,
                            items: list[dict], source_call_id: str) -> int:
    written = 0
    for item in items:
        if not isinstance(item, dict) or "name" not in item:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO procurement_items"
            " (shop_id, purchase_date, name_normalized, display_name, amount, supplier, source_call_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (shop_id, purchase_date, normalize(item["name"]), item["name"],
             item.get("amount"), item.get("supplier"), source_call_id),
        )
        written += 1
    return written


def clear_shop_day(conn: sqlite3.Connection, shop_id: str, date: str) -> None:
    """Remove a day's rows so a re-ingest cannot leave stale line items behind.

    INSERT OR REPLACE alone would keep procurement rows that the corrected call
    no longer mentions, because they are keyed by product name.
    """
    conn.execute("DELETE FROM procurement_items WHERE shop_id = ? AND purchase_date = ?", (shop_id, date))


# ------------------------------------------------------------------ vendors (P1)


def upsert_vendor(
    conn: sqlite3.Connection,
    *,
    shop_id: str,
    display_name: str,
    goods: list[str] | None = None,
    phone_e164: str | None = None,
    notes: str | None = None,
    now: str,
) -> str:
    """Create or update a vendor for a shop. Returns ``vendor_id``.

    Phone may be null until the owner provides E.164 — never invent one.
    Lookup key is ``(shop_id, normalized display name)``.
    """
    key = normalize(display_name)
    if not key:
        raise StoreError("vendor display_name is required")
    vendor_id = _vendor_id(shop_id, key)
    goods_json = json.dumps(list(goods or []), ensure_ascii=False)
    conn.execute(
        "INSERT INTO vendors"
        " (vendor_id, shop_id, display_name, name_normalized, phone_e164,"
        "  goods_json, notes, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(shop_id, name_normalized) DO UPDATE SET"
        "   display_name = excluded.display_name,"
        "   phone_e164 = COALESCE(excluded.phone_e164, vendors.phone_e164),"
        "   goods_json = CASE"
        "     WHEN excluded.goods_json = '[]' THEN vendors.goods_json"
        "     ELSE excluded.goods_json END,"
        "   notes = COALESCE(excluded.notes, vendors.notes),"
        "   updated_at = excluded.updated_at",
        (vendor_id, shop_id, display_name.strip(), key, phone_e164,
         goods_json, notes, now, now),
    )
    row = conn.execute(
        "SELECT vendor_id FROM vendors WHERE shop_id = ? AND name_normalized = ?",
        (shop_id, key),
    ).fetchone()
    return row["vendor_id"]


def find_vendor_by_name(
    conn: sqlite3.Connection, *, shop_id: str, name: str
) -> sqlite3.Row | None:
    """Lookup a saved vendor by spoken name (normalized)."""
    return conn.execute(
        "SELECT * FROM vendors WHERE shop_id = ? AND name_normalized = ?",
        (shop_id, normalize(name)),
    ).fetchone()


def list_vendors(conn: sqlite3.Connection, *, shop_id: str) -> list[dict]:
    """Return vendors for a shop with phones masked for safe display."""
    rows = conn.execute(
        "SELECT * FROM vendors WHERE shop_id = ? ORDER BY display_name",
        (shop_id,),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["phone_masked"] = mask_phone(item.get("phone_e164"))
        item["goods"] = json.loads(item.get("goods_json") or "[]")
        out.append(item)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or inspect the SQLite ledger")
    parser.add_argument("--init", type=Path, metavar="DB", help="Create the schema at this path")
    parser.add_argument("--info", type=Path, metavar="DB", help="Show row counts")
    args = parser.parse_args()

    if args.init:
        conn = connect(args.init)
        initialize(conn)
        print(f"Ledger ready at {args.init} (schema v{schema_version(conn)})")
        conn.close()
        return 0

    if args.info:
        try:
            conn = connect(args.info, read_only=True)
        except StoreError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"schema v{schema_version(conn)}")
        for table in ("shops", "products", "inventory_readings", "daily_sales",
                      "procurement_items", "call_receipts", "vendors",
                      "restock_requests", "orders"):
            n = conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
            print(f"  {table:<20} {n}")
        conn.close()
        return 0

    parser.error("give --init or --info")


if __name__ == "__main__":
    sys.exit(main())
