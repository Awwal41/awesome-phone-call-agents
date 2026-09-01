#!/usr/bin/env python3
"""Voice Shop Manager — runner. Preview by default; live calls are opt-in.

Default and `--fixture` paths place no call and need no credentials. A real
call requires BOTH `--execute` and `--confirm-recipient-opt-in`, as specified
in skills/shop-voice-checkin/references/safety.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILL = ROOT.parents[2] / "skills" / "shop-voice-checkin"
FIXTURES = ROOT / "fixtures"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def schema_path(call_type: str) -> Path:
    name = "result-schema-inventory.json" if call_type == "inventory" else "result-schema-sales.json"
    return SKILL / "references" / name


def build_task(request: dict) -> str:
    shop = request.get("shop_id", "the shop")
    products = ", ".join(request.get("products_to_ask", ["stock items"]))
    style = request.get("language_style", "english")
    minutes = request.get("max_minutes", 4)
    if request["call_type"] == "inventory":
        tone = "Pidgin-influenced English" if style == "pidgin-english" else "plain English"
        return (
            f"Call the consenting shop owner for a short morning inventory check-in at {shop}. "
            f"Use {tone}. Ask about: {products}. Capture approximate quantities and units. "
            f"Ask what is running low. Disclose you are an AI shop manager assistant. "
            f"Keep under {minutes} minutes. Do not give financial advice."
        )
    return (
        f"Call the consenting shop owner for a short evening sales recap at {shop}. "
        f"Ask roughly how much they sold today, top sellers, and any restock purchases. "
        f"Disclose you are an AI shop manager assistant. Keep under {minutes} minutes. "
        f"Do not give financial advice."
    )


def preview(request: dict) -> dict:
    return {
        "mode": "demo",
        "side_effects": "none — no CALL-E network call",
        "phone_masked": request["phone"][:6] + "****" + request["phone"][-2:],
        "region": request["region"],
        "locale": request["locale"],
        "call_type": request["call_type"],
        "task": build_task(request),
        "result_schema": load_json(schema_path(request["call_type"])),
        "idempotency_key": (
            f"shopvoice-{request['shop_id']}-{request['call_type']}-DEMO"
        ),
    }


def demo_summary(shop_id: str, method: str = "turnover") -> str:
    """Compute the weekly summary from the fixture call results.

    Nothing here is hardcoded. `demo_ledger.build` runs the fixtures through
    the production path — `ingest.ingest_call` into a real SQLite ledger built
    by `store.py` — and summarize.py derives every figure from it. Only the
    *input* is a fixture instead of a CALL-E result, so the numbers change if
    the fixtures change and the demo cannot drift from live behaviour.
    """
    import sqlite3
    import tempfile

    import summarize
    from demo_ledger import build

    with tempfile.TemporaryDirectory() as tmp:
        ledger = build(Path(tmp) / "demo.db")
        conn = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            summary = summarize.build_summary(conn, shop_id, method=method)
        finally:
            conn.close()

    return (
        summarize.render_text(summary)
        + "\n\nComputed from fixture call results — not a live retailer."
    )


def run_demo(request: dict, fixture_name: str | None) -> dict:
    if fixture_name:
        fixture = FIXTURES / fixture_name
    else:
        fixture = (
            FIXTURES / "inventory-result.json"
            if request["call_type"] == "inventory"
            else FIXTURES / "sales-result.json"
        )
    if not fixture.is_file():
        raise SystemExit(f"Missing fixture: {fixture}")
    return {
        "preview": preview(request),
        "structured_result": load_json(fixture),
        "demo_note": "Fixture result — simulates a completed CALL-E call without placing one.",
    }


def run_live(args) -> int:
    """Place one real call, then ingest it through the same path as the demo."""
    import live_call

    request = load_json(args.request)

    if not args.confirm_recipient_opt_in:
        print(
            "Live calls require --confirm-recipient-opt-in.\n"
            "Confirm the shop owner has opted in, then re-run with both flags.",
            file=sys.stderr,
        )
        return 2

    if not request.get("recipient_consented"):
        print(
            f"{args.request}: recipient_consented is not true. "
            "Do not place a call the owner has not agreed to.",
            file=sys.stderr,
        )
        return 2

    api_key = os.environ.get("CALLE_API_KEY")
    if not api_key:
        print("CALLE_API_KEY is not set. Export it, then re-run.", file=sys.stderr)
        return 2

    call_date = args.call_date or date.today().isoformat()

    try:
        base_url = live_call.resolve_base_url()
        client = live_call.build_client(api_key, base_url)
        result = live_call.execute_live(
            request,
            client,
            task=build_task(request),
            schema=load_json(schema_path(request["call_type"])),
            provider_hash=live_call.provider_account_hash(api_key),
            call_date=call_date,
        )
    except live_call.LiveCallError as exc:
        print(f"Live call failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.db:
        import ingest
        import store

        conn = store.connect(args.db)
        store.initialize(conn)
        try:
            verdict = ingest.ingest_call(conn, result)
        finally:
            conn.close()
        print(f"\nLedger: {verdict}", file=sys.stderr)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Voice Shop Manager demo (default: no live call)"
    )
    parser.add_argument(
        "--request",
        type=Path,
        default=ROOT / "example_request.json",
        help="Request JSON path",
    )
    parser.add_argument(
        "--fixture",
        type=str,
        default=None,
        help="Fixture filename under fixtures/ (default by call_type)",
    )
    parser.add_argument(
        "--weekly-summary",
        action="store_true",
        help="Compute and print the weekly business summary from the fixture ledger",
    )
    parser.add_argument(
        "--slow-moving-method",
        choices=("turnover", "top-sellers"),
        default="turnover",
        help="How slow-moving stock is identified (see fixtures/README.md)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Place a REAL CALL-E call. Requires --confirm-recipient-opt-in.",
    )
    parser.add_argument(
        "--confirm-recipient-opt-in",
        action="store_true",
        help="Required with --execute: the recipient has consented to be called.",
    )
    parser.add_argument(
        "--call-date",
        default=None,
        help="Ledger date for the call (default: today). Also fixes the idempotency key.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="With --execute: ingest the result into this SQLite ledger.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=argparse.SUPPRESS,  # deprecated alias, kept so old commands fail loudly
    )
    args = parser.parse_args()

    if args.live:
        print(
            "--live has been renamed. Use the spelling the safety docs specify:\n"
            "  --execute --confirm-recipient-opt-in",
            file=sys.stderr,
        )
        return 2

    if args.execute:
        return run_live(args)

    request = load_json(args.request)
    payload = run_demo(request, args.fixture)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.weekly_summary:
        print()
        print(demo_summary(request["shop_id"], args.slow_moving_method))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
