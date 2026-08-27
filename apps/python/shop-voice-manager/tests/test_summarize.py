"""Tests for the weekly summary. No credentials, no network, no calls placed.

Refs #18, #19.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = APP_ROOT / "fixtures"

import summarize  # noqa: E402
from demo_ledger import CONFIDENCE_THRESHOLD, build  # noqa: E402

WEEK_START, WEEK_END = "2026-08-10", "2026-08-16"
SHOP = "demo-lagos-corner-shop"


def golden(name: str) -> dict:
    return json.loads((FIXTURES / "expected" / name).read_text(encoding="utf-8"))


def summarize_week(conn, **kwargs):
    return summarize.build_summary(conn, SHOP, WEEK_START, WEEK_END, **kwargs)


# ---------------------------------------------------------------- goldens

@pytest.mark.parametrize("method", ["turnover", "top-sellers"])
def test_matches_golden(ledger, method):
    assert summarize_week(ledger, method=method) == golden(f"summary-{method}.json")


def test_headline_figures_match_fixture_reconciliation(ledger):
    expected = golden("weekly-summary.json")
    summary = summarize_week(ledger)

    assert summary["estimated_revenue"] == expected["estimated_revenue"]
    assert summary["procurement_spend"] == expected["procurement_spend"]
    assert summary["estimated_gross"] == expected["estimated_gross"]
    assert summary["products_running_low"] == expected["products_running_low"]
    assert summary["days_with_data"] == expected["days_with_data"]


def test_narrative_matches_demo_script(ledger):
    lines = summarize_week(ledger)["narrative"].splitlines()
    assert lines[0] == "This week you sold about ₦425,000. You spent about ₦310,000 restocking."
    assert lines[1] == "Products running low: Indomie, Sugar."
    assert lines[2].startswith("Approximate capital in slow-moving stock: ₦")


# ---------------------------------------------------------------- the two methods

def test_turnover_method_finds_only_genuinely_dead_stock(ledger):
    names = [p["name"] for p in summarize_week(ledger, method="turnover")["slow_moving_products"]]
    assert names == ["Milo"]


def test_top_sellers_method_misclassifies_a_fast_mover(ledger):
    """Cooking oil turns over 63% of held stock yet is never a top seller by revenue.

    This is why the turnover method is the default.
    """
    products = summarize_week(ledger, method="top-sellers")["slow_moving_products"]
    oil = next(p for p in products if p["name"] == "Cooking oil")

    assert oil["turnover"] > 0.6
    assert oil["ever_top_seller"] is False


def test_threshold_controls_sensitivity(ledger):
    wide = summarize_week(ledger, method="turnover", threshold=0.7)
    assert {p["name"] for p in wide["slow_moving_products"]} == {"Milo", "Cooking oil"}

    narrow = summarize_week(ledger, method="turnover", threshold=0.05)
    assert narrow["slow_moving_products"] == []
    assert narrow["slow_moving_capital"] == 0


def test_capital_is_quantity_times_unit_cost(ledger):
    for product in summarize_week(ledger)["slow_moving_products"]:
        assert product["capital_estimate"] == round(product["quantity_estimate"] * product["unit_cost"])


# ---------------------------------------------------------------- ingest gating

def test_low_confidence_result_is_not_written_to_the_ledger(full_ledger):
    rows = full_ledger.execute(
        "SELECT * FROM daily_sales WHERE sales_date = '2026-08-18'"
    ).fetchall()
    assert rows == []

    receipt = full_ledger.execute(
        "SELECT * FROM call_receipts WHERE call_id = 'call_sal_20260818_lowconf'"
    ).fetchone()
    assert receipt is not None
    assert receipt["task_completed"] == 1, "the call claimed success"
    assert receipt["confidence"] < CONFIDENCE_THRESHOLD, "but confidence is what gates ingest"


def test_unanswered_calls_leave_a_receipt_but_no_data(full_ledger):
    for call_id, status in [("call_inv_20260817_noanswer", "no_answer"),
                            ("call_sal_20260817_voicemail", "voicemail")]:
        receipt = full_ledger.execute(
            "SELECT status FROM call_receipts WHERE call_id = ?", (call_id,)
        ).fetchone()
        assert receipt["status"] == status

    assert full_ledger.execute(
        "SELECT COUNT(*) c FROM inventory_readings WHERE reading_date = '2026-08-17'"
    ).fetchone()["c"] == 0


def test_refused_consent_writes_nothing(full_ledger):
    assert full_ledger.execute(
        "SELECT COUNT(*) c FROM inventory_readings WHERE reading_date = '2026-08-18'"
    ).fetchone()["c"] == 0


def test_partial_check_in_does_not_zero_untouched_products(full_ledger):
    readings = full_ledger.execute(
        "SELECT name_normalized FROM inventory_readings WHERE reading_date = '2026-08-19'"
    ).fetchall()
    assert {r["name_normalized"] for r in readings} == {"rice", "indomie"}

    milo = full_ledger.execute(
        "SELECT quantity_estimate FROM products WHERE name_normalized = 'milo'"
    ).fetchone()
    assert milo["quantity_estimate"] == 9


# ---------------------------------------------------------------- robustness

def test_short_week_still_summarises(ledger):
    summary = summarize.build_summary(ledger, SHOP, "2026-08-10", "2026-08-12")
    assert summary["days_with_data"] == 3
    assert summary["estimated_revenue"] == 171500


def test_week_defaults_to_the_last_recorded_day(ledger):
    summary = summarize.build_summary(ledger, SHOP)
    assert summary["week_end"] == WEEK_END
    assert summary["week_start"] == WEEK_START


def test_unknown_shop_is_an_error(ledger):
    with pytest.raises(summarize.SummaryError):
        summarize.build_summary(ledger, "no-such-shop", WEEK_START, WEEK_END)


def test_empty_range_reports_nothing_rather_than_crashing(ledger):
    summary = summarize.build_summary(ledger, SHOP, "2026-01-01", "2026-01-07")
    assert summary["estimated_revenue"] == 0
    assert summary["products_running_low"] == []
    assert summary["slow_moving_products"] == []


def test_output_is_deterministic(ledger):
    assert summarize_week(ledger) == summarize_week(ledger)


# ---------------------------------------------------------------- rendering

def test_currency_symbol_follows_the_shop(ledger):
    assert summarize.money(1000, "NGN") == "₦1,000"
    assert summarize.money(1000, "INR") == "₹1,000"
    assert summarize.money(1000, "KES") == "KES 1,000"
    assert summarize.money(None, "NGN") == "not known"


def test_text_render_includes_the_narrative_and_totals(ledger):
    text = summarize.render_text(summarize_week(ledger))
    assert "Ada Corner Shop" in text
    assert "This week you sold about ₦425,000" in text
    assert "Milo" in text


def test_cli_emits_valid_json(ledger, tmp_path, capsys):
    path = build(tmp_path / "cli.db")
    assert summarize.main(["--db", str(path), "--shop-id", SHOP, "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["estimated_revenue"] == 425000


def test_cli_rejects_a_missing_ledger(capsys):
    assert summarize.main(["--db", "/nonexistent/shop.db", "--shop-id", SHOP]) == 1
    assert "No ledger" in capsys.readouterr().err
