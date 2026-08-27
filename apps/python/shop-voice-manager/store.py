#!/usr/bin/env python3
"""SQLite ledger for Voice Shop Manager.

Owns the schema and the write primitives. It holds no policy about which calls
are worth recording — that belongs in `ingest.py`, because policy changes far
more often than schema does.

    python3 store.py --init shop.db

Schema contract: SCHEMA.md. Refs #14.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

SCHEMA_VERSION = 1

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
CREATE INDEX IF NOT EXISTS idx_readings_shop_date ON inventory_readings(shop_id, reading_date);
CREATE INDEX IF NOT EXISTS idx_sales_shop_date ON daily_sales(shop_id, sales_date);
CREATE INDEX IF NOT EXISTS idx_receipts_shop ON call_receipts(shop_id, created_at);
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
    """Create the schema if absent. Safe to call on an existing ledger."""
    with conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO schema_meta (key, value) VALUES ('version', ?)"
            " ON CONFLICT(key) DO NOTHING",
            (str(SCHEMA_VERSION),),
        )


def schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM schema_meta WHERE key = 'version'").fetchone()
    return int(row["value"]) if row else 0


def check_compatible(conn: sqlite3.Connection) -> None:
    found = schema_version(conn)
    if found != SCHEMA_VERSION:
        raise StoreError(
            f"Ledger is schema version {found}, this code expects {SCHEMA_VERSION}. "
            "Rebuild the ledger or add a migration."
        )


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
                      "procurement_items", "call_receipts"):
            n = conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
            print(f"  {table:<20} {n}")
        conn.close()
        return 0

    parser.error("give --init or --info")


if __name__ == "__main__":
    sys.exit(main())
