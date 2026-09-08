#!/usr/bin/env python3
"""HTTP API and static host for the Shop Check-In console.

Standard library only, because the app declares `dependencies = []` and a test
asserts it stays that way. `http.server` is enough for a single-operator
console; it is not a public web server and should not be exposed to the
internet.

Additive by construction: this package imports the existing modules and does
not modify them. Deleting `web/` leaves the CLI and the ledger untouched.

Everything is configuration, not code:

    CALLE_API_KEY     required to place a real call. Never read by the browser.
    SHOPVOICE_DB      ledger path            (default: ./shop.db)
    SHOPVOICE_HOST    bind address           (default: 127.0.0.1)
    SHOPVOICE_PORT    port                   (default: 8765)
    SHOPVOICE_DEMO    "1" replays a stored call instead of dialling
    CALLE_BASE_URL    honoured by live_call, allowlisted there

Run:  python3 web/server.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
import uuid
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

APP_ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
sys.path.insert(0, str(APP_ROOT))

import client            # noqa: E402  (build_task, schema_path, load_json)
import ingest            # noqa: E402
import live_call         # noqa: E402
import store             # noqa: E402

DB_PATH = Path(os.environ.get("SHOPVOICE_DB", APP_ROOT / "shop.db"))
RESULTS_DIR = Path(os.environ.get("SHOPVOICE_RESULTS", DB_PATH.parent / "call-results"))
FIXTURES = APP_ROOT / "fixtures" / "calls"
DEMO = os.environ.get("SHOPVOICE_DEMO") == "1"

# Region support is a property of the CALL-E account, so it is configuration.
# Anything not listed is offered but flagged; the operator decides.
SUPPORTED = [r.strip() for r in os.environ.get(
    "SHOPVOICE_REGIONS", "NG,GH,KE,ZA,US,GB,CA,IN,AU,SG,AE,PH").split(",") if r.strip()]
BLOCKED = {r.strip() for r in os.environ.get("SHOPVOICE_BLOCKED_REGIONS", "").split(",") if r.strip()}
# Currencies offered per shop. The first is the default for a new shop.
CURRENCIES = [c.strip().upper() for c in os.environ.get(
    "SHOPVOICE_CURRENCIES",
    "NGN,GHS,KES,ZAR,INR,USD,GBP,EUR,CAD,AUD,SGD,AED,PHP").split(",") if c.strip()]
# Units a shop owner actually says on the phone. Suggestions, not a whitelist:
# the field stays free text so an unusual unit is never blocked.
UNITS = [u.strip() for u in os.environ.get(
    "SHOPVOICE_UNITS",
    # Nigeria
    "bags,cartons,kegs,pieces,sachets,crates,tins,bottles,packs,"
    "rolls,baskets,bundles,cups,dericas,paint rubbers,"
    # India
    "kg,litres,packets,dozens,sacks,quintals,strips").split(",") if u.strip()]

# A "voice" is the one question an operator can actually answer: what should
# the owner hear? Locale and style are the two fields underneath it, and
# keeping them as separate dropdowns made the form answer a question nobody
# asked.
VOICES = [
    {"id": "english",        "name": "English",         "locale": "en", "style": "english"},
    {"id": "pidgin-english", "name": "Nigerian Pidgin", "locale": "en", "style": "pidgin-english"},
    {"id": "hindi",          "name": "Hindi",           "locale": "hi", "style": "english"},
]
VOICE_BY_ID = {v["id"]: v for v in VOICES}

# Reference data, not business configuration: dialling codes and country names
# do not change per deployment. SHOPVOICE_REGIONS still decides which of these
# are offered, and every default below is only a default.
COUNTRY_INFO = {
    "NG": ("Nigeria",        "234", "NGN", "pidgin-english"),
    "GH": ("Ghana",          "233", "GHS", "english"),
    "KE": ("Kenya",          "254", "KES", "english"),
    "ZA": ("South Africa",    "27", "ZAR", "english"),
    "IN": ("India",           "91", "INR", "hindi"),
    "US": ("United States",    "1", "USD", "english"),
    "GB": ("United Kingdom",  "44", "GBP", "english"),
    "CA": ("Canada",           "1", "CAD", "english"),
    "AU": ("Australia",       "61", "AUD", "english"),
    "SG": ("Singapore",       "65", "SGD", "english"),
    "AE": ("United Arab Emirates", "971", "AED", "english"),
    "PH": ("Philippines",     "63", "PHP", "english"),
}


def countries() -> list[dict]:
    """Offered countries, each carrying the defaults it implies."""
    out = []
    for code in SUPPORTED:
        name, dial, currency, voice = COUNTRY_INFO.get(
            code, (code, "", CURRENCIES[0], VOICES[0]["id"]))
        out.append({
            "code": code, "name": name, "dial": dial,
            # only suggest a currency the deployment actually offers
            "currency": currency if currency in CURRENCIES else CURRENCIES[0],
            "voice": voice if voice in VOICE_BY_ID else VOICES[0]["id"],
            "blocked": code in BLOCKED,
        })
    return out

# Lists are read once at import, so a running server can be older than the
# files on disk. The console needs to be able to say so.
STARTED_AT = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
CONFIG_KEYS = ("regions", "blocked", "currencies", "units", "locales", "styles")

RUNS: dict[str, dict] = {}
RUNS_LOCK = threading.Lock()


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def _conn():
    conn = store.connect(DB_PATH)
    store.initialize(conn)
    return conn


def _rows(conn, sql, args=()):
    return [dict(r) for r in conn.execute(sql, args)]


def raw_result(call_id: str) -> dict | None:
    """The full CALL-E response, which is where transcripts live.

    Live results are written to RESULTS_DIR as they land. Fixture calls are
    read from their source file, so history predating the console still opens.
    """
    saved = RESULTS_DIR / f"{call_id}.json"
    if saved.is_file():
        try:
            return json.loads(saved.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    for path in sorted(FIXTURES.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("call_id") == call_id:
            return payload
    return None


def transcript_of(payload: dict) -> list[dict]:
    for recipient in payload.get("recipients") or []:
        for attempt in recipient.get("attempts") or []:
            turns = attempt.get("transcript_turns") or []
            if turns:
                return [{"at": t.get("offset_seconds", 0),
                         "who": t.get("speaker", "bot"),
                         "text": t.get("text", "")} for t in turns]
    return []


def duration_of(payload: dict) -> int | None:
    for recipient in payload.get("recipients") or []:
        for attempt in recipient.get("attempts") or []:
            if attempt.get("duration_seconds"):
                return int(attempt["duration_seconds"])
            start, end = attempt.get("started_at"), attempt.get("completed_at")
            if start and end:
                try:
                    fmt = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
                    return int((fmt(end) - fmt(start)).total_seconds())
                except ValueError:
                    pass
    return None


def checkpoint_stats(shop_ids: list[str]) -> dict[str, dict]:
    """Attempt counts per shop, read once from the checkpoints.

    A shop id can contain dashes, so the key is matched against the known ids
    rather than parsed, longest first: "alpha-mall" must not swallow a key
    belonging to "alpha-mall-annex".
    """
    provider_hash = live_call.provider_account_hash(
        os.environ.get("CALLE_API_KEY") or "demo")
    folder = live_call.STATE_DIR / provider_hash
    stats = {sid: {"placed": 0, "failed": 0, "last": None} for sid in shop_ids}
    if not folder.is_dir():
        return stats
    ordered = sorted(shop_ids, key=len, reverse=True)
    for path in folder.glob("*.json"):
        try:
            cp = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        key = cp.get("idempotency_key") or ""
        sid = next((s for s in ordered if key.startswith(f"shopvoice-{s}-")), None)
        if sid is None:
            continue
        bucket = stats[sid]
        if cp.get("call_id"):
            bucket["placed"] += 1
        else:
            bucket["failed"] += 1
        when = cp.get("updated_at")
        if when and (bucket["last"] is None or when > bucket["last"]):
            bucket["last"] = when
    return stats


def customers() -> list[dict]:
    conn = _conn()
    try:
        shops = _rows(conn, "SELECT * FROM shops ORDER BY COALESCE(display_name, id)")
        counts = {r["shop_id"]: r for r in _rows(conn,
            "SELECT shop_id, COUNT(*) AS calls, MAX(created_at) AS last_call"
            " FROM call_receipts GROUP BY shop_id")}
        attempts = checkpoint_stats([s["id"] for s in shops])
        for shop in shops:
            stat = counts.get(shop["id"], {})
            tried = attempts.get(shop["id"], {})
            shop["calls"] = stat.get("calls", 0)
            # attempts that never became a ledger row still happened
            shop["failed"] = tried.get("failed", 0)
            shop["last_call"] = stat.get("last_call") or tried.get("last")
            shop["products"] = [r["display_name"] for r in _rows(conn,
                "SELECT display_name FROM products WHERE shop_id = ? ORDER BY display_name",
                (shop["id"],))]
        return shops
    finally:
        conn.close()


def customer(shop_id: str) -> dict:
    conn = _conn()
    try:
        rows = _rows(conn, "SELECT * FROM shops WHERE id = ?", (shop_id,))
        if not rows:
            raise ApiError(404, f"No shop with id {shop_id!r}.")
        shop = rows[0]
        shop["products"] = _rows(conn,
            "SELECT display_name AS name, unit, quantity_estimate, running_low"
            " FROM products WHERE shop_id = ? ORDER BY display_name", (shop_id,))
        return shop
    finally:
        conn.close()


def calls_for(shop_id: str) -> list[dict]:
    conn = _conn()
    try:
        receipts = _rows(conn,
            "SELECT * FROM call_receipts WHERE shop_id = ? ORDER BY created_at DESC", (shop_id,))
        for r in receipts:
            readings = _rows(conn,
                "SELECT display_name AS name, quantity_estimate AS qty, unit, running_low"
                " FROM inventory_readings WHERE source_call_id = ? ORDER BY display_name",
                (r["call_id"],))
            sales = _rows(conn,
                "SELECT sales_date, estimated_revenue, procurement_spend, top_sellers_json"
                " FROM daily_sales WHERE source_call_id = ?", (r["call_id"],))
            r["products"] = readings
            r["low"] = sum(1 for x in readings if x["running_low"])
            if sales:
                r["revenue"] = sales[0]["estimated_revenue"]
                r["spend"] = sales[0]["procurement_spend"]
                r["date"] = sales[0]["sales_date"]
            elif readings:
                dates = _rows(conn,
                    "SELECT DISTINCT reading_date FROM inventory_readings WHERE source_call_id = ?",
                    (r["call_id"],))
                r["date"] = dates[0]["reading_date"] if dates else r["created_at"][:10]
            else:
                r["date"] = r["created_at"][:10]
        return receipts
    finally:
        conn.close()


def attempts_for(shop_id: str) -> list[dict]:
    """Calls that were attempted, from the checkpoints.

    The ledger only records calls that completed and passed the confidence
    gate, so a refused or failed call leaves no trace there. An operator still
    needs to see it: "no calls yet" after two failed attempts is a lie, and it
    hides the reason they failed.
    """
    provider_hash = live_call.provider_account_hash(
        os.environ.get("CALLE_API_KEY") or "demo")
    folder = live_call.STATE_DIR / provider_hash
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.glob("*.json")):
        try:
            cp = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        key = cp.get("idempotency_key") or ""
        if not key.startswith(f"shopvoice-{shop_id}-"):
            continue
        rest = key[len(f"shopvoice-{shop_id}-"):]
        parts = rest.split("-")
        if len(parts) < 4:
            continue
        out.append({
            "call_id": cp.get("call_id"),
            "call_type": parts[0],
            "date": "-".join(parts[1:4]),
            "phase": cp.get("phase"),
            "status": cp.get("status"),
            "error": cp.get("error"),
            "created_at": cp.get("updated_at") or "",
        })
    return out


def today_for(shop_id: str) -> dict:
    """What has already been dialled for this shop today.

    Consults the checkpoints as well as the ledger. Checkpoints outlive the
    database on purpose: a ledger can be rebuilt from call results, but a call
    that already rang someone cannot be un-placed. Reading only the ledger
    means a wiped database offers a "first" call that would silently resume the
    previous one instead of dialling.
    """
    shop = customer(shop_id)
    today = date.today().isoformat()
    ledger = [c for c in calls_for(shop["id"]) if c.get("date") == today]
    provider_hash = live_call.provider_account_hash(
        os.environ.get("CALLE_API_KEY") or "demo")
    attempts = {
        call_type: live_call.next_attempt(provider_hash, shop["id"], call_type, today) - 1
        for call_type in ("inventory", "sales")
    }
    return {
        "date": today,
        "calls": [{"call_id": c["call_id"], "call_type": c["call_type"]} for c in ledger],
        "attempts": attempts,
        "dialled": {k: v > 0 for k, v in attempts.items()},
    }


def call_detail(call_id: str) -> dict:
    conn = _conn()
    try:
        rows = _rows(conn, "SELECT * FROM call_receipts WHERE call_id = ?", (call_id,))
    finally:
        conn.close()
    payload = raw_result(call_id)
    if not rows and not payload:
        raise ApiError(404, f"No call with id {call_id!r}.")
    detail = rows[0] if rows else {"call_id": call_id}
    if rows:
        shop_calls = [c for c in calls_for(rows[0]["shop_id"]) if c["call_id"] == call_id]
        if shop_calls:
            detail = shop_calls[0]
    if payload:
        structured = payload.get("structured_result") or {}
        detail["transcript"] = transcript_of(payload)
        detail["duration"] = duration_of(payload)
        detail["evidence"] = payload.get("evidence") or []
        detail["notes"] = structured.get("owner_notes") or ""
        detail["top_sellers"] = structured.get("top_sellers") or []
        detail["procurement"] = structured.get("procurement_items") or []
        detail["raw_products"] = structured.get("products") or []
    if detail.get("shop_id"):
        try:
            detail["currency"] = customer(detail["shop_id"])["currency"]
        except ApiError:
            pass
    detail.setdefault("currency", CURRENCIES[0])
    detail.setdefault("transcript", [])
    detail.setdefault("evidence", [])
    detail.setdefault("notes", "")
    return detail


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

def save_customer(body: dict) -> dict:
    voice = VOICE_BY_ID.get(str(body.get("voice") or ""))
    if voice and not body.get("locale"):
        body["locale"] = voice["locale"]
    body.setdefault("locale", VOICES[0]["locale"])
    for field in ("shop_id", "phone", "region", "locale"):
        if not str(body.get(field) or "").strip():
            raise ApiError(400, f"{field} is required.")
    profile = {
        "shop_id": body["shop_id"].strip(),
        "display_name": (body.get("display_name") or "").strip() or body["shop_id"].strip(),
        "phone": body["phone"].strip(),
        "region": body["region"].strip().upper(),
        "locale": body["locale"].strip(),
        "currency": (body.get("currency") or CURRENCIES[0]).strip().upper(),
        "language_style": (body.get("language_style")
                           or VOICE_BY_ID.get(str(body.get("voice") or ""), {}).get("style")
                           or VOICES[0]["style"]),
        "consent_timestamp": body.get("consent_timestamp") or _now(),
        "typical_products": [
            {"name": p["name"].strip(), "unit": (p.get("unit") or "").strip() or None}
            for p in (body.get("products") or []) if str(p.get("name") or "").strip()
        ],
    }
    if body.get("create"):
        conn = _conn()
        try:
            taken = _rows(conn, "SELECT id FROM shops WHERE id = ?", (profile["shop_id"],))
        finally:
            conn.close()
        if taken:
            raise ApiError(409,
                f"The ID {profile['shop_id']!r} is already taken. "
                "Pick a different name, or open the existing shop.")
    conn = _conn()
    try:
        with conn:
            store.upsert_shop(conn, profile)
            store.seed_products(conn, profile)
    finally:
        conn.close()
    return customer(profile["shop_id"])


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_request(shop: dict, body: dict) -> dict:
    """The request dict the existing CLI path already understands."""
    products = [p["name"] for p in (body.get("products") or []) if str(p.get("name") or "").strip()]
    if not products:
        products = [p["name"] for p in shop.get("products", [])]
    if not products:
        raise ApiError(400, "Add at least one product to ask about.")
    return {
        "workflow_id": body.get("workflow_id") or f"console-{uuid.uuid4().hex[:8]}",
        "call_type": body.get("call_type") or "inventory",
        "phone": shop["phone_e164"],
        "region": shop["region"],
        "locale": shop["locale"],
        "currency": shop["currency"],
        "shop_id": shop["id"],
        "recipient_consented": True,
        "language_style": body.get("language_style")
                          or shop.get("language_style") or VOICES[0]["style"],
        "products_to_ask": products,
        "max_minutes": int(body.get("max_minutes") or 4),
    }


def start_checkin(body: dict) -> dict:
    if not body.get("consent"):
        raise ApiError(400, "Consent must be recorded before a call can be placed.")
    shop = customer(str(body.get("shop_id") or ""))
    if shop["region"].upper() in BLOCKED:
        raise ApiError(400,
            f"{shop['region'].upper()} is not enabled on this account. "
            "CALL-E rejects the call at creation, so it is refused here instead.")

    api_key = os.environ.get("CALLE_API_KEY")
    if not api_key and not DEMO:
        raise ApiError(400,
            "CALLE_API_KEY is not set on the server. Export it and restart, "
            "or set SHOPVOICE_DEMO=1 to replay a stored call.")

    request = build_request(shop, body)
    call_date = body.get("call_date") or date.today().isoformat()

    # "One call per shop per type per day" is the safety default. A repeat is
    # allowed but must be asked for, and its key stays derived so a crash-retry
    # still resumes rather than dialling again.
    provider_hash = live_call.provider_account_hash(api_key or "demo")
    attempt = (live_call.next_attempt(provider_hash, shop["id"],
                                      request["call_type"], call_date)
               if body.get("again") else 1)

    key = uuid.uuid4().hex[:12]
    with RUNS_LOCK:
        RUNS[key] = {"key": key, "phase": "queued", "elapsed": 0.0, "status": "queued",
                     "call_type": request["call_type"],
                     "demo": DEMO, "shop_id": shop["id"], "started": time.time(),
                     "masked_phone": live_call.mask_phone(shop["phone_e164"]),
                     "attempt": attempt,
                     "call_id": None, "error": None, "done": False, "result": None}
    target = _demo_run if DEMO else _live_run
    threading.Thread(target=target, args=(key, request, call_date, api_key, attempt),
                     daemon=True).start()
    return {"key": key, "demo": DEMO, "attempt": attempt}


def _set(key: str, **fields):
    with RUNS_LOCK:
        if key in RUNS:
            RUNS[key].update(fields)


def _persist(key: str, result: dict, request: dict):
    call_id = result.get("call_id")
    if call_id:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        (RESULTS_DIR / f"{call_id}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    conn = _conn()
    try:
        with conn:
            store.upsert_shop(conn, {**request, "display_name": request.get("shop_id")})
        verdict = ingest.ingest_call(conn, result)
    finally:
        conn.close()
    _set(key, done=True, phase="completed", status=result.get("status", "completed"),
         call_id=call_id, result={"verdict": str(verdict), "call_id": call_id})


def _live_run(key: str, request: dict, call_date: str, api_key: str, attempt: int = 1):
    def progress(elapsed: float, status: str):
        phase = "completed" if status in live_call.TERMINAL_STATUSES else "in_progress"
        _set(key, elapsed=round(elapsed, 1), status=status, phase=phase)
    try:
        _set(key, phase="ringing")
        base_url = live_call.resolve_base_url()
        calle = live_call.build_client(api_key, base_url)
        result = live_call.execute_live(
            request, calle,
            task=client.build_task(request),
            schema=client.load_json(client.schema_path(request["call_type"])),
            provider_hash=live_call.provider_account_hash(api_key),
            call_date=call_date,
            attempt=attempt,
            progress=progress,
        )
        _persist(key, result, request)
    except Exception as exc:                       # surfaced to the operator
        traceback.print_exc()
        _set(key, done=True, phase="failed", error=str(exc))


def _demo_run(key: str, request: dict, call_date: str, _api_key, attempt: int = 1):
    """Replay the newest stored call at wall-clock speed. No call is placed."""
    source = None
    for path in sorted(RESULTS_DIR.glob("*.json"), reverse=True) + \
                sorted(FIXTURES.glob("*.json"), reverse=True):
        try:
            source = json.loads(path.read_text(encoding="utf-8"))
            break
        except (json.JSONDecodeError, OSError):
            continue
    if source is None:
        _set(key, done=True, phase="failed", error="No stored call to replay.")
        return
    turns = transcript_of(source)
    total = (turns[-1]["at"] if turns else 30) + 4
    _set(key, phase="ringing", status="ringing")
    started = time.time()
    while True:
        elapsed = time.time() - started
        if elapsed >= total:
            break
        _set(key, elapsed=round(elapsed, 1), phase="in_progress", status="in_progress")
        time.sleep(0.5)
    _set(key, done=True, phase="completed", status="completed",
         call_id=source.get("call_id"),
         result={"verdict": "demo replay, nothing written", "call_id": source.get("call_id")})


def run_status(key: str) -> dict:
    with RUNS_LOCK:
        run = RUNS.get(key)
        if not run:
            raise ApiError(404, "Unknown run.")
        return dict(run)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

ROUTES_GET = {}
ROUTES_POST = {}


class Handler(BaseHTTPRequestHandler):
    server_version = "ShopVoiceConsole/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s %s\n" % (self.address_string(), fmt % args))

    def _send(self, status: int, body: bytes, ctype: str):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload):
        self._send(status, json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _static(self, path: str):
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (STATIC / name).resolve()
        if not str(target).startswith(str(STATIC.resolve())) or not target.is_file():
            self._json(404, {"error": "Not found."})
            return
        types = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".json": "application/json",
                 ".svg": "image/svg+xml", ".ico": "image/x-icon"}
        self._send(200, target.read_bytes(), types.get(target.suffix, "application/octet-stream"))

    def do_GET(self):
        route = urlparse(self.path).path
        try:
            if not route.startswith("/api/"):
                return self._static(route)
            parts = [p for p in route[5:].split("/") if p]
            if parts == ["config"]:
                return self._json(200, {
                    "live": bool(os.environ.get("CALLE_API_KEY")),
                    "demo": DEMO, "db": str(DB_PATH),
                    "started_at": STARTED_AT, "config_keys": list(CONFIG_KEYS),
                    "regions": SUPPORTED, "blocked": sorted(BLOCKED),
                    "currencies": CURRENCIES, "units": UNITS,
                    "countries": countries(), "voices": VOICES,
                })
            if parts == ["customers"]:
                return self._json(200, {"customers": customers()})
            if len(parts) == 2 and parts[0] == "customers":
                return self._json(200, customer(parts[1]))
            if len(parts) == 3 and parts[0] == "customers" and parts[2] == "calls":
                ledger = calls_for(parts[1])
                seen = {c["call_id"] for c in ledger}
                with RUNS_LOCK:
                    live = [dict(r) for r in RUNS.values()
                            if r.get("shop_id") == parts[1] and not r.get("done")]
                running = [{
                    "key": r["key"],
                    "call_id": r.get("call_id") or ("run-" + r["key"]),
                    "call_type": r.get("call_type") or "inventory",
                    "date": date.today().isoformat(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "outcome": "running", "phase": r.get("phase"),
                    "elapsed": r.get("elapsed", 0),
                    "accepted": 0, "confidence": None, "products": [], "low": 0,
                } for r in live]
                unrecorded = [
                    {**a, "accepted": 0, "confidence": None, "products": [], "low": 0,
                     "outcome": "failed",
                     "call_id": a["call_id"] or ("attempt-" + a["created_at"])}
                    for a in attempts_for(parts[1])
                    if a["call_id"] not in seen and a.get("phase") != "finished"
                ]
                merged = sorted(running + ledger + unrecorded,
                                key=lambda c: c.get("created_at") or "", reverse=True)
                return self._json(200, {"calls": merged})
            if len(parts) == 3 and parts[0] == "customers" and parts[2] == "today":
                return self._json(200, today_for(parts[1]))
            if len(parts) == 2 and parts[0] == "calls":
                return self._json(200, call_detail(parts[1]))
            if len(parts) == 2 and parts[0] == "checkins":
                return self._json(200, run_status(parts[1]))
            self._json(404, {"error": "Unknown endpoint."})
        except ApiError as exc:
            self._json(exc.status, {"error": exc.message})
        except Exception as exc:
            traceback.print_exc()
            self._json(500, {"error": str(exc)})

    do_HEAD = do_GET

    def do_POST(self):
        route = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}") if length else {}
            parts = [p for p in route[5:].split("/") if p] if route.startswith("/api/") else []
            if parts == ["customers"]:
                return self._json(200, save_customer(body))
            if parts == ["checkins"]:
                return self._json(202, start_checkin(body))
            self._json(404, {"error": "Unknown endpoint."})
        except ApiError as exc:
            self._json(exc.status, {"error": exc.message})
        except json.JSONDecodeError:
            self._json(400, {"error": "Body must be JSON."})
        except Exception as exc:
            traceback.print_exc()
            self._json(500, {"error": str(exc)})


def _watch_and_reload():
    """Restart when a source file changes, so an edit does not need a manual
    restart. Opt in with SHOPVOICE_RELOAD=1.

    Never restarts while a call is in flight: the run state lives in memory,
    and losing it mid-call would leave the operator with no status for a call
    that is still ringing someone. The checkpoint would still protect the
    budget, but the console would go blind, so the reload simply waits.
    """
    watched = [Path(__file__).resolve()] + [
        APP_ROOT / name for name in
        ("live_call.py", "client.py", "ingest.py", "store.py", "summarize.py")
    ]
    stamps = {}
    for path in watched:
        try:
            stamps[path] = path.stat().st_mtime
        except OSError:
            pass
    while True:
        time.sleep(1.0)
        for path, was in list(stamps.items()):
            try:
                now = path.stat().st_mtime
            except OSError:
                continue
            if now == was:
                continue
            with RUNS_LOCK:
                busy = any(not r.get("done") for r in RUNS.values())
            if busy:
                continue                       # try again on the next tick
            print(f"\n  {path.name} changed, restarting")
            sys.stdout.flush()
            os.execv(sys.executable, [sys.executable] + sys.argv)


def main() -> int:
    host = os.environ.get("SHOPVOICE_HOST", "127.0.0.1")
    port = int(os.environ.get("SHOPVOICE_PORT", "8765"))
    conn = _conn()
    conn.close()
    mode = "DEMO replay" if DEMO else ("live" if os.environ.get("CALLE_API_KEY") else "read only")
    if os.environ.get("SHOPVOICE_RELOAD") == "1":
        threading.Thread(target=_watch_and_reload, daemon=True).start()

    print(f"Shop Check-In console on http://{host}:{port}")
    print(f"  ledger  {DB_PATH}")
    print(f"  mode    {mode}")
    print(f"  started {STARTED_AT}"
          + ("  (auto-reload on)" if os.environ.get("SHOPVOICE_RELOAD") == "1" else ""))
    if not os.environ.get("CALLE_API_KEY") and not DEMO:
        print("  note    export CALLE_API_KEY to place calls, or SHOPVOICE_DEMO=1 to replay")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
