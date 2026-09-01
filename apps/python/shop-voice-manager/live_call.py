#!/usr/bin/env python3
"""Live CALL-E execution for the shop check-in.

This module supplies the *input* that `demo_ledger.py` supplies from fixtures.
Everything downstream is unchanged: the result goes through
`ingest.ingest_call`, which applies the confidence gate and writes through
`store.py`. The demo path and the live path therefore cannot drift apart.

    demo_ledger.py ─┐
                    ├─→ ingest.ingest_call() ─→ store.py ─→ summarize.py
    live_call.py ───┘

Nothing here places a call on import. `execute_live` needs a client object,
and `client.py` only builds one under `--execute --confirm-recipient-opt-in`.

Refs #15 (R5).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

APP_ROOT = Path(__file__).resolve().parent
STATE_DIR = APP_ROOT / ".call-state"

DEFAULT_BASE_URL = "https://api.heycall-e.com"
TRUSTED_BASE_URLS = frozenset({DEFAULT_BASE_URL})

CHECKPOINT_VERSION = 1
POLL_INTERVAL_SECONDS = 5.0
DEFAULT_TIMEOUT_SECONDS = 600.0

# Statuses CALL-E can end on. Mirrors ingest.TERMINAL_WITHOUT_DATA plus success.
TERMINAL_STATUSES = {
    "completed", "no_answer", "voicemail", "busy", "declined",
    "canceled", "cancelled", "expired", "failed",
}


class LiveCallError(RuntimeError):
    """Raised when the live path cannot proceed safely."""


# --------------------------------------------------------------------------
# Base URL — refuse anything that is not the real CALL-E host
# --------------------------------------------------------------------------

def normalize_trusted_base_url(value: str | None) -> str:
    raw = str(value or DEFAULT_BASE_URL).strip().rstrip("/")
    if raw.endswith("/v1"):
        raw = raw[:-3].rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https":
        raise LiveCallError("CALLE_BASE_URL must use https.")
    if parsed.username or parsed.password:
        raise LiveCallError("CALLE_BASE_URL must not include credentials.")
    if parsed.params or parsed.query or parsed.fragment:
        raise LiveCallError("CALLE_BASE_URL must not include a query string or fragment.")
    if parsed.path not in {"", "/"}:
        raise LiveCallError("CALLE_BASE_URL must be a host URL only.")
    normalized = f"https://{parsed.netloc.lower()}"
    if normalized not in TRUSTED_BASE_URLS:
        raise LiveCallError(
            f"CALLE_BASE_URL must be a trusted CALL-E host. Use {DEFAULT_BASE_URL}"
        )
    return normalized


def resolve_base_url() -> str:
    return normalize_trusted_base_url(os.environ.get("CALLE_BASE_URL"))


def provider_account_hash(api_key: str) -> str:
    """Scope checkpoints to an account without ever storing the key."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:24]


# --------------------------------------------------------------------------
# Request shaping
# --------------------------------------------------------------------------

def idempotency_key(shop_id: str, call_type: str, call_date: str) -> str:
    """One key per shop per call type per day, as specified in PROJECT_PLAN.md.

    The demo path emits `…-DEMO`. The live path must use the real date so a
    retry after a crash cannot place a second call.
    """
    return f"shopvoice-{shop_id}-{call_type}-{call_date}"


def build_recipients(request: dict) -> list[dict]:
    for field in ("phone", "region", "locale"):
        if not request.get(field):
            raise LiveCallError(
                f"request is missing {field!r} — never guess phone, region, or locale"
            )
    return [{
        "phones": [request["phone"]],
        "region": request["region"],
        "locale": request["locale"],
    }]


def mask_phone(phone: str) -> str:
    return phone[:6] + "****" + phone[-2:] if len(phone) > 8 else "****"


# --------------------------------------------------------------------------
# Checkpoints — a crash must never cause a second call
# --------------------------------------------------------------------------

def checkpoint_path(provider_hash: str, key: str) -> Path:
    slug = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return STATE_DIR / provider_hash / f"{slug}.json"


def read_checkpoint(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LiveCallError(
            f"Checkpoint {path.name} is corrupt. Inspect it before retrying — "
            "deleting it may cause a duplicate call."
        ) from exc
    if not isinstance(payload, dict):
        raise LiveCallError(f"Checkpoint {path.name} is not an object.")
    if payload.get("version") not in (None, CHECKPOINT_VERSION):
        raise LiveCallError(f"Checkpoint {path.name} has an unsupported version.")
    return payload


def write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = dict(payload, version=CHECKPOINT_VERSION)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(body, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)  # atomic — a half-written checkpoint is worse than none


# --------------------------------------------------------------------------
# Response normalisation — the SDK may hand back objects or dicts
# --------------------------------------------------------------------------

def _field(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_dict(obj: Any) -> dict:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    for attr in ("model_dump", "to_dict", "dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                out = fn()
                if isinstance(out, dict):
                    return out
            except TypeError:
                pass
    return {k: v for k, v in vars(obj).items() if not k.startswith("_")}


def to_ingest_shape(call: Any, request: dict, *, call_date: str, key: str) -> dict:
    """Normalise a CALL-E response into the shape `ingest.ingest_call` accepts.

    The fixtures under `fixtures/calls/` are the specification for this shape;
    keep them and this function in step.
    """
    raw = _as_dict(call)
    call_id = _field(call, "id") or _field(call, "call_id")
    if not isinstance(call_id, str) or not call_id:
        raise LiveCallError("CALL-E response carried no call id.")

    confidence = _as_dict(_field(call, "completion_confidence"))
    structured = _field(call, "structured_result")
    if structured is not None and not isinstance(structured, dict):
        structured = _as_dict(structured)

    shaped = {
        "call_id": call_id,
        "idempotency_key": key,
        "status": _field(call, "status", "unknown"),
        "task_completed": bool(_field(call, "task_completed", False)),
        "completion_confidence": confidence,
        "structured_result": structured,
        "metadata": {
            "shop_id": request["shop_id"],
            "call_type": request["call_type"],
            "call_date": call_date,
        },
    }
    recipients = raw.get("recipients")
    if recipients:
        shaped["recipients"] = recipients
    return shaped


# --------------------------------------------------------------------------
# The call
# --------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _poll_until_terminal(client: Any, call_id: str, *, timeout_seconds: float,
                         sleep=time.sleep, monotonic=time.monotonic) -> Any:
    deadline = monotonic() + timeout_seconds
    latest = None
    while monotonic() < deadline:
        latest = client.calls.get(call_id)
        if _field(latest, "status") in TERMINAL_STATUSES:
            return latest
        sleep(POLL_INTERVAL_SECONDS)
    raise LiveCallError(
        f"Call {call_id} did not reach a terminal status within "
        f"{timeout_seconds:.0f}s. It may still be running — check the CALL-E "
        f"dashboard before retrying, or the retry may duplicate it."
    )


def execute_live(request: dict, client: Any, *, task: str, schema: dict,
                 provider_hash: str, call_date: str | None = None,
                 timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
                 sleep=time.sleep, monotonic=time.monotonic) -> dict:
    """Place one call and return a result in `ingest.ingest_call` shape.

    Crash-safe: the checkpoint records the call id the moment CALL-E returns
    one, so a rerun polls the existing call instead of placing a second.
    """
    if not request.get("recipient_consented"):
        raise LiveCallError(
            "request.recipient_consented is not true — the recipient must opt "
            "in before any live call."
        )

    call_date = call_date or date.today().isoformat()
    key = idempotency_key(request["shop_id"], request["call_type"], call_date)
    checkpoint = checkpoint_path(provider_hash, key)
    state = read_checkpoint(checkpoint)

    call_id = state.get("call_id")
    if isinstance(call_id, str) and call_id:
        # A previous run already created this call. Never create it again.
        latest = client.calls.get(call_id)
        if _field(latest, "status") not in TERMINAL_STATUSES:
            latest = _poll_until_terminal(
                client, call_id, timeout_seconds=timeout_seconds,
                sleep=sleep, monotonic=monotonic)
    else:
        write_checkpoint(checkpoint, {
            "phase": "reserved",
            "provider_account_hash": provider_hash,
            "idempotency_key": key,
            "masked_phone": mask_phone(request["phone"]),
            "updated_at": _now(),
        })
        created = client.calls.create(
            task=task,
            recipients=build_recipients(request),
            result_schema=schema,
            idempotency_key=key,
        )
        call_id = _field(created, "id") or _field(created, "call_id")
        if not isinstance(call_id, str) or not call_id:
            write_checkpoint(checkpoint, {
                "phase": "create_failed",
                "provider_account_hash": provider_hash,
                "idempotency_key": key,
                "updated_at": _now(),
            })
            raise LiveCallError("CALL-E create response carried no call id.")
        write_checkpoint(checkpoint, {
            "phase": "created",
            "call_id": call_id,
            "provider_account_hash": provider_hash,
            "idempotency_key": key,
            "masked_phone": mask_phone(request["phone"]),
            "updated_at": _now(),
        })
        latest = created if _field(created, "status") in TERMINAL_STATUSES else \
            _poll_until_terminal(client, call_id, timeout_seconds=timeout_seconds,
                                 sleep=sleep, monotonic=monotonic)

    write_checkpoint(checkpoint, {
        "phase": "finished",
        "call_id": call_id,
        "provider_account_hash": provider_hash,
        "idempotency_key": key,
        "masked_phone": mask_phone(request["phone"]),
        "status": _field(latest, "status", "unknown"),
        "updated_at": _now(),
    })
    return to_ingest_shape(latest, request, call_date=call_date, key=key)


def build_client(api_key: str, base_url: str) -> Any:
    """Import and construct the SDK client. Imported lazily so the demo path,
    the tests, and `--help` never need `calle-ai` installed."""
    try:
        from calle import CalleClient
    except ImportError as exc:
        raise LiveCallError(
            "The CALL-E SDK is not installed. Run: pip install 'calle-ai>=0.1.0'"
        ) from exc
    return CalleClient(api_key=api_key, base_url=base_url)
