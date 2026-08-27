#!/usr/bin/env python3
"""Voice Shop Manager — demo runner (preview + fixtures, no live call by default)."""

from __future__ import annotations

import argparse
import json
import sys
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


def demo_summary() -> str:
    return (
        "=== Voice Shop Manager — weekly demo summary ===\n"
        "Shop: Ada Corner Shop (demo-lagos-corner-shop)\n"
        "This week estimated sales: NGN 425,000\n"
        "Restock spend: NGN 310,000\n"
        "Estimated gross margin: NGN 115,000\n"
        "Running low: Indomie, Sugar\n"
        "Capital in slow-moving stock: ~NGN 85,000 (Milo — barely sold this week)\n"
        "==============================================\n"
        "Source: fixture data only — not a live retailer."
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
        help="Print demo weekly business summary",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="[Not implemented in demo] Place real CALL-E call — use Rajput's SDK path",
    )
    args = parser.parse_args()

    if args.live:
        print(
            "Live calls are not enabled in this demo build.\n"
            "Set CALLE_API_KEY and use the full SDK client (R5) when ready.\n"
            "For hackathon demo, run without --live.",
            file=sys.stderr,
        )
        return 1

    request = load_json(args.request)
    payload = run_demo(request, args.fixture)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.weekly_summary:
        print()
        print(demo_summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
