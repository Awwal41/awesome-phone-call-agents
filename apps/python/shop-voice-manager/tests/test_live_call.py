"""Tests for the live CALL-E path (R5).

Every test here uses a stub client. Nothing imports the CALL-E SDK, reads a
credential, or touches the network — see test_no_live_calls.py, which enforces
that for the whole suite.

The property that matters most: a crash after CALL-E creates a call must never
result in a second call. The checkpoint is what guarantees it, so it is tested
directly rather than assumed.
"""

from __future__ import annotations

import json

import pytest

import ingest
import live_call
import store


REQUEST = {
    "workflow_id": "test-inventory-001",
    "call_type": "inventory",
    "phone": "+2348000000000",
    "region": "NG",
    "locale": "en",
    "currency": "NGN",
    "shop_id": "demo-lagos-corner-shop",
    "recipient_consented": True,
    "products_to_ask": ["Rice"],
}

RESULT = {
    "check_in_completed": True,
    "products": [{"name": "Rice", "quantity_estimate": 12, "unit": "bags"}],
}


class StubCall:
    def __init__(self, call_id="call_test_1", status="completed",
                 task_completed=True, score=0.93, structured_result=None):
        self.id = call_id
        self.status = status
        self.task_completed = task_completed
        self.completion_confidence = {"score": score, "label": "high"}
        self.structured_result = RESULT if structured_result is None else structured_result


class StubCalls:
    """Records every create so a duplicate call is impossible to miss."""

    def __init__(self, created=None, get_sequence=None):
        self.created = created or StubCall()
        self.create_calls = []
        self.get_calls = []
        self._get_sequence = list(get_sequence or [])

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return self.created

    def get(self, call_id):
        self.get_calls.append(call_id)
        if self._get_sequence:
            return self._get_sequence.pop(0)
        return self.created


class StubClient:
    def __init__(self, **kwargs):
        self.calls = StubCalls(**kwargs)


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Never write checkpoints into the working tree during tests."""
    monkeypatch.setattr(live_call, "STATE_DIR", tmp_path / ".call-state")


@pytest.fixture
def schema():
    return {"type": "object"}


def run(client, request=None, **kwargs):
    return live_call.execute_live(
        request or REQUEST, client,
        task="test task", schema={"type": "object"},
        provider_hash="testhash", call_date="2026-09-01",
        sleep=lambda _s: None, **kwargs)


# --------------------------------------------------------------------------
# Base URL is an allowlist, not a suggestion
# --------------------------------------------------------------------------

def test_default_base_url_is_the_calle_host():
    assert live_call.normalize_trusted_base_url(None) == "https://api.heycall-e.com"  # allow-host-literal


@pytest.mark.parametrize("bad", [
    "http://api.heycall-e.com",   # not https  # allow-host-literal
    "https://evil.example.com",              # not the CALL-E host
    "https://user:pw@api.heycall-e.com",   # credentials  # allow-host-literal
    "https://api.heycall-e.com/path",   # path  # allow-host-literal
    "https://api.heycall-e.com?x=1",   # query  # allow-host-literal
])
def test_untrusted_base_urls_are_refused(bad):
    with pytest.raises(live_call.LiveCallError):
        live_call.normalize_trusted_base_url(bad)


def test_v1_suffix_is_tolerated():
    assert live_call.normalize_trusted_base_url(
        "https://api.heycall-e.com/v1") == "https://api.heycall-e.com"  # allow-host-literal


# --------------------------------------------------------------------------
# Consent and inputs
# --------------------------------------------------------------------------

def test_call_without_consent_is_refused_before_any_client_use():
    client = StubClient()
    with pytest.raises(live_call.LiveCallError, match="recipient_consented"):
        run(client, {**REQUEST, "recipient_consented": False})
    assert client.calls.create_calls == []


@pytest.mark.parametrize("missing", ["phone", "region", "locale"])
def test_missing_routing_fields_are_never_guessed(missing):
    with pytest.raises(live_call.LiveCallError, match=missing):
        live_call.build_recipients({k: v for k, v in REQUEST.items() if k != missing})


def test_api_key_is_hashed_not_stored():
    digest = live_call.provider_account_hash("secret-key")
    assert "secret-key" not in digest
    assert len(digest) == 24


def test_phone_is_masked_in_checkpoints(tmp_path):
    client = StubClient()
    run(client)
    written = list((tmp_path / ".call-state").rglob("*.json"))
    assert written, "expected a checkpoint"
    body = written[0].read_text(encoding="utf-8")
    assert REQUEST["phone"] not in body
    assert "****" in body


# --------------------------------------------------------------------------
# Idempotency — the property that protects the 20-call budget
# --------------------------------------------------------------------------

def test_idempotency_key_matches_the_documented_format():
    assert live_call.idempotency_key("shop-a", "inventory", "2026-09-01") == \
        "shopvoice-shop-a-inventory-2026-09-01"


def test_key_is_sent_to_calle():
    client = StubClient()
    run(client)
    assert client.calls.create_calls[0]["idempotency_key"] == \
        "shopvoice-demo-lagos-corner-shop-inventory-2026-09-01"


def test_rerun_after_a_crash_polls_instead_of_calling_again():
    """The whole point of the checkpoint: one call, even if we crash mid-flight."""
    first = StubClient()
    run(first)
    assert len(first.calls.create_calls) == 1

    second = StubClient()          # fresh client, same checkpoint directory
    result = run(second)
    assert second.calls.create_calls == [], "a second call was placed"
    assert second.calls.get_calls == ["call_test_1"]
    assert result["call_id"] == "call_test_1"


def test_a_response_without_a_call_id_is_an_error_not_a_silent_pass():
    client = StubClient(created=StubCall(call_id=""))
    with pytest.raises(live_call.LiveCallError, match="call id"):
        run(client)


def test_a_corrupt_checkpoint_refuses_rather_than_risking_a_duplicate(tmp_path):
    client = StubClient()
    run(client)
    checkpoint = next((tmp_path / ".call-state").rglob("*.json"))
    checkpoint.write_text("{not json", encoding="utf-8")
    with pytest.raises(live_call.LiveCallError, match="corrupt"):
        run(StubClient())


# --------------------------------------------------------------------------
# Polling
# --------------------------------------------------------------------------

def test_a_pending_call_is_polled_until_terminal():
    pending = StubCall(status="in_progress")
    done = StubCall(status="completed")
    client = StubClient(created=pending, get_sequence=[pending, done])
    result = run(client)
    assert result["status"] == "completed"


def test_a_call_that_never_finishes_times_out_loudly():
    pending = StubCall(status="in_progress")
    client = StubClient(created=pending, get_sequence=[pending] * 50)
    ticks = iter([0.0] + [1000.0] * 50)
    with pytest.raises(live_call.LiveCallError, match="terminal status"):
        run(client, timeout_seconds=1.0, monotonic=lambda: next(ticks))


# --------------------------------------------------------------------------
# The result must be the shape ingest already understands
# --------------------------------------------------------------------------

def test_result_carries_the_metadata_ingest_requires():
    result = run(StubClient())
    assert result["metadata"] == {
        "shop_id": "demo-lagos-corner-shop",
        "call_type": "inventory",
        "call_date": "2026-09-01",
    }


def test_a_live_result_ingests_exactly_like_a_fixture(tmp_path):
    result = run(StubClient())

    conn = store.connect(tmp_path / "live.db")
    store.initialize(conn)
    profile = json.loads(
        (live_call.APP_ROOT / "fixtures" / "shop-profile.json").read_text(encoding="utf-8"))
    with conn:
        store.upsert_shop(conn, profile)
    verdict = ingest.ingest_call(conn, result)
    conn.close()

    assert verdict.accepted
    assert verdict.rows_written == 1


def test_a_low_confidence_live_result_is_rejected_by_the_same_gate(tmp_path):
    client = StubClient(created=StubCall(score=0.41))
    result = run(client)

    conn = store.connect(tmp_path / "live.db")
    store.initialize(conn)
    profile = json.loads(
        (live_call.APP_ROOT / "fixtures" / "shop-profile.json").read_text(encoding="utf-8"))
    with conn:
        store.upsert_shop(conn, profile)
    verdict = ingest.ingest_call(conn, result)
    receipts = conn.execute("SELECT COUNT(*) FROM call_receipts").fetchone()[0]
    conn.close()

    assert not verdict.accepted
    assert verdict.rows_written == 0
    assert receipts == 1, "a rejected call must still leave a receipt"


def test_an_unanswered_live_call_writes_no_data():
    client = StubClient(created=StubCall(
        status="no_answer", task_completed=False, structured_result={}))
    result = run(client)
    assert result["status"] == "no_answer"
    assert result["task_completed"] is False


def test_dict_responses_work_as_well_as_objects():
    """The SDK may hand back either; neither should need a special path."""
    client = StubClient(created={
        "id": "call_dict_1", "status": "completed", "task_completed": True,
        "completion_confidence": {"score": 0.9}, "structured_result": RESULT,
    })
    result = run(client)
    assert result["call_id"] == "call_dict_1"
    assert result["completion_confidence"]["score"] == 0.9
