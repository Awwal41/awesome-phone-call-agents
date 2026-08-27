#!/usr/bin/env python3
"""Weekly business summary for a shop, computed locally from the SQLite ledger.

Reads only. Places no calls, needs no credentials, touches no network.

    python3 summarize.py --db shop.db --shop-id demo-lagos-corner-shop
    python3 summarize.py --db shop.db --shop-id demo-lagos-corner-shop --format json

Refs #18. Ledger shape is documented in SCHEMA.md.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

CURRENCY_SYMBOLS = {"NGN": "₦", "INR": "₹", "USD": "$", "GBP": "£", "EUR": "€"}

DEFAULT_TURNOVER_THRESHOLD = 0.25
DEFAULT_WEEK_DAYS = 7


class SummaryError(Exception):
    pass


def money(amount: float | None, currency: str) -> str:
    if amount is None:
        return "not known"
    symbol = CURRENCY_SYMBOLS.get(currency.upper(), currency.upper() + " ")
    return f"{symbol}{round(amount):,}"


def approximate(amount: float) -> int:
    """Round to the nearest thousand. The owner spoke in approximations."""
    return int(round(amount / 1000.0) * 1000)


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise SummaryError(f"No ledger at {db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_shop(conn: sqlite3.Connection, shop_id: str) -> dict:
    row = conn.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)).fetchone()
    if row is None:
        raise SummaryError(f"Shop {shop_id!r} is not in the ledger")
    return dict(row)


def resolve_week(conn: sqlite3.Connection, shop_id: str, start: str | None, end: str | None) -> tuple[str, str]:
    if start and end:
        return start, end

    row = conn.execute(
        """
        SELECT MAX(d) AS latest FROM (
            SELECT MAX(sales_date) AS d FROM daily_sales WHERE shop_id = ?
            UNION ALL
            SELECT MAX(reading_date) AS d FROM inventory_readings WHERE shop_id = ?
        )
        """,
        (shop_id, shop_id),
    ).fetchone()

    latest = row["latest"] if row else None
    if not latest:
        raise SummaryError(f"No call data recorded for shop {shop_id!r}")

    end = end or latest
    if not start:
        start = (date.fromisoformat(end) - timedelta(days=DEFAULT_WEEK_DAYS - 1)).isoformat()
    return start, end


def load_sales(conn: sqlite3.Connection, shop_id: str, start: str, end: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM daily_sales WHERE shop_id = ? AND sales_date BETWEEN ? AND ? ORDER BY sales_date",
        (shop_id, start, end),
    ).fetchall()
    out = []
    for row in rows:
        record = dict(row)
        try:
            record["top_sellers"] = json.loads(record.get("top_sellers_json") or "[]")
        except json.JSONDecodeError:
            record["top_sellers"] = []
        out.append(record)
    return out


def load_readings(conn: sqlite3.Connection, shop_id: str, start: str, end: str) -> dict[str, list[dict]]:
    rows = conn.execute(
        """
        SELECT * FROM inventory_readings
        WHERE shop_id = ? AND reading_date BETWEEN ? AND ?
        ORDER BY reading_date
        """,
        (shop_id, start, end),
    ).fetchall()
    by_product: dict[str, list[dict]] = {}
    for row in rows:
        by_product.setdefault(row["name_normalized"], []).append(dict(row))
    return by_product


def load_restock_units(conn: sqlite3.Connection, shop_id: str, start: str, end: str) -> dict[str, float]:
    """Convert restocking spend into units using each product's last known cost."""
    rows = conn.execute(
        """
        SELECT pi.name_normalized AS name, SUM(pi.amount) AS spend, p.last_cost AS cost
        FROM procurement_items pi
        LEFT JOIN products p
          ON p.shop_id = pi.shop_id AND p.name_normalized = pi.name_normalized
        WHERE pi.shop_id = ? AND pi.purchase_date BETWEEN ? AND ?
        GROUP BY pi.name_normalized, p.last_cost
        """,
        (shop_id, start, end),
    ).fetchall()

    units: dict[str, float] = {}
    for row in rows:
        if row["cost"]:
            units[row["name"]] = (row["spend"] or 0) / row["cost"]
    return units


def load_costs(conn: sqlite3.Connection, shop_id: str) -> dict[str, float | None]:
    rows = conn.execute(
        "SELECT name_normalized, last_cost FROM products WHERE shop_id = ?", (shop_id,)
    ).fetchall()
    return {row["name_normalized"]: row["last_cost"] for row in rows}


def load_call_counts(conn: sqlite3.Connection, shop_id: str, start: str, end: str) -> dict:
    rows = conn.execute(
        """
        SELECT status, task_completed, COUNT(*) AS n
        FROM call_receipts
        WHERE shop_id = ? AND substr(created_at, 1, 10) BETWEEN ? AND ?
        GROUP BY status, task_completed
        """,
        (shop_id, start, end),
    ).fetchall()

    placed = sum(row["n"] for row in rows)
    completed = sum(row["n"] for row in rows if row["status"] == "completed" and row["task_completed"])
    return {"calls_placed": placed, "calls_completed": completed}


def movement(readings: list[dict], restocked: float) -> dict:
    quantities = [r["quantity_estimate"] for r in readings if r["quantity_estimate"] is not None]
    if not quantities:
        return {"consumed": None, "average_held": None, "turnover": None}

    average_held = sum(quantities) / len(quantities)
    consumed = quantities[0] - quantities[-1] + restocked
    turnover = (consumed / average_held) if average_held else None
    return {
        "consumed": round(consumed, 2),
        "average_held": round(average_held, 2),
        "turnover": round(turnover, 4) if turnover is not None else None,
    }


def find_slow_movers(
    readings: dict[str, list[dict]],
    restock_units: dict[str, float],
    costs: dict[str, float | None],
    top_sellers_seen: set[str],
    method: str,
    threshold: float,
) -> tuple[list[dict], list[str]]:
    slow, unpriced = [], []

    for name, entries in sorted(readings.items()):
        latest = entries[-1]
        stats = movement(entries, restock_units.get(name, 0.0))

        if method == "top-sellers":
            is_slow = name not in top_sellers_seen
        else:
            is_slow = stats["turnover"] is not None and stats["turnover"] < threshold

        if not is_slow:
            continue

        quantity = latest["quantity_estimate"]
        cost = costs.get(name)
        capital = round(quantity * cost) if quantity is not None and cost else None
        if capital is None:
            unpriced.append(latest["display_name"])

        slow.append({
            "name": latest["display_name"],
            "quantity_estimate": quantity,
            "unit": latest["unit"],
            "unit_cost": cost,
            "capital_estimate": capital,
            "consumed": stats["consumed"],
            "average_held": stats["average_held"],
            "turnover": stats["turnover"],
            "ever_top_seller": name in top_sellers_seen,
        })

    return slow, unpriced


def build_summary(
    conn: sqlite3.Connection,
    shop_id: str,
    start: str | None = None,
    end: str | None = None,
    method: str = "turnover",
    threshold: float = DEFAULT_TURNOVER_THRESHOLD,
) -> dict:
    shop = load_shop(conn, shop_id)
    start, end = resolve_week(conn, shop_id, start, end)

    sales = load_sales(conn, shop_id, start, end)
    readings = load_readings(conn, shop_id, start, end)
    restock_units = load_restock_units(conn, shop_id, start, end)
    costs = load_costs(conn, shop_id)

    revenue = sum(row["estimated_revenue"] or 0 for row in sales)
    spend = sum(row["procurement_spend"] or 0 for row in sales)
    top_sellers_seen = {s.strip().lower() for row in sales for s in row["top_sellers"] if isinstance(s, str)}

    latest_date = max((entries[-1]["reading_date"] for entries in readings.values()), default=None)
    running_low = sorted(
        entries[-1]["display_name"]
        for entries in readings.values()
        if entries[-1]["reading_date"] == latest_date and entries[-1]["running_low"]
    )

    slow, unpriced = find_slow_movers(readings, restock_units, costs, top_sellers_seen, method, threshold)
    priced = [item["capital_estimate"] for item in slow if item["capital_estimate"] is not None]

    summary = {
        "shop_id": shop_id,
        "display_name": shop.get("display_name"),
        "currency": shop.get("currency") or "NGN",
        "week_start": start,
        "week_end": end,
        "days_with_data": len({row["sales_date"] for row in sales} | set()),
        "estimated_revenue": round(revenue),
        "procurement_spend": round(spend),
        "estimated_gross": round(revenue - spend),
        "products_running_low": running_low,
        "slow_moving_method": method,
        "slow_moving_products": slow,
        "slow_moving_capital": sum(priced) if priced else 0,
    }
    if method == "turnover":
        summary["turnover_threshold"] = threshold
    summary.update(load_call_counts(conn, shop_id, start, end))
    if unpriced:
        summary["capital_unknown_for"] = sorted(unpriced)

    summary["narrative"] = render_narrative(summary)
    return summary


def render_narrative(summary: dict) -> str:
    currency = summary["currency"]
    lines = [
        f"This week you sold about {money(approximate(summary['estimated_revenue']), currency)}. "
        f"You spent about {money(approximate(summary['procurement_spend']), currency)} restocking."
    ]

    low = summary["products_running_low"]
    lines.append(f"Products running low: {', '.join(low)}." if low else "Nothing is running low right now.")

    if summary["slow_moving_products"]:
        lines.append(
            "Approximate capital in slow-moving stock: "
            f"{money(approximate(summary['slow_moving_capital']), currency)}."
        )
    return "\n".join(lines)


def render_text(summary: dict) -> str:
    currency = summary["currency"]
    name = summary.get("display_name") or summary["shop_id"]

    out = [
        f"Weekly summary for {name}",
        f"{summary['week_start']} to {summary['week_end']}",
        "",
        summary["narrative"],
        "",
        f"  Sales            {money(summary['estimated_revenue'], currency)}",
        f"  Restocking       {money(summary['procurement_spend'], currency)}",
        f"  Rough gross      {money(summary['estimated_gross'], currency)}",
        f"  Days with data   {summary['days_with_data']}",
        f"  Calls completed  {summary['calls_completed']} of {summary['calls_placed']} placed",
    ]

    if summary["slow_moving_products"]:
        out += ["", f"Slow-moving stock ({summary['slow_moving_method']} method)"]
        for item in summary["slow_moving_products"]:
            held = f"{item['quantity_estimate']:g} {item['unit']}" if item["unit"] else f"{item['quantity_estimate']:g}"
            turnover = f"{item['turnover'] * 100:.0f}% turnover" if item["turnover"] is not None else "movement unknown"
            out.append(f"  {item['name']:<14} {held:<14} {money(item['capital_estimate'], currency):<12} {turnover}")

    if summary.get("capital_unknown_for"):
        out += ["", f"No cost on record for: {', '.join(summary['capital_unknown_for'])}"]

    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Weekly shop summary from the local ledger")
    parser.add_argument("--db", type=Path, required=True, help="Path to the SQLite ledger")
    parser.add_argument("--shop-id", required=True)
    parser.add_argument("--week-start", help="YYYY-MM-DD, defaults to six days before the last recorded day")
    parser.add_argument("--week-end", help="YYYY-MM-DD, defaults to the last recorded day")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--slow-moving-method",
        choices=("turnover", "top-sellers"),
        default="turnover",
        help="turnover compares consumption against stock held; top-sellers flags anything never named a best seller",
    )
    parser.add_argument("--turnover-threshold", type=float, default=DEFAULT_TURNOVER_THRESHOLD)
    args = parser.parse_args(argv)

    if not 0 < args.turnover_threshold <= 1:
        parser.error("--turnover-threshold must be between 0 and 1")

    try:
        with connect(args.db) as conn:
            summary = build_summary(
                conn,
                args.shop_id,
                args.week_start,
                args.week_end,
                args.slow_moving_method,
                args.turnover_threshold,
            )
    except SummaryError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except sqlite3.DatabaseError as exc:
        print(f"Cannot read ledger: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render_text(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
