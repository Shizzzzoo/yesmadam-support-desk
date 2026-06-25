# Provider Coordination Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a customer-waiting ticket (no-show / "where's my pro") arrives, proactively alert the assigned professional, let their choice (late / reschedule / can't make it / on-site) or their 5-minute silence drive the resolution, and guarantee no refund-and-cancel ever fires while a professional is committed.

**Architecture:** Extend the existing event-driven Lemma pod. A new `provider_responses` table holds one coordination row per alert; `handle_ticket` gains an `alert_provider` branch; a new `provider_reply` workflow (fires on `provider_responses` UPDATE) routes the pro's decision; a `provider-sla` time schedule sweeps overdue rows into `no_response`. A `provider_state` lock on `bookings` blocks refunds (from any ticket) while a pro is committed, reusing the existing proof-of-service gate pattern.

**Tech Stack:** Lemma pod bundle (JSONC resource configs + Python `code.py` functions using `lemma_sdk`), `lemma` CLI for import/run, Python 3.11 + pydantic locally. Spec: `docs/superpowers/specs/2026-06-25-provider-coordination-loop-design.md`.

---

## Conventions used by every task

**Working dir:** `/home/sahl/Documents/lemma/support-desk` unless stated.

**This is not a git repo yet.** Step 0 (below) initialises one so the per-task commits work. If the user declines git, replace each `git commit` step with "save files."

**Pure-helper test pattern.** Lemma functions are single-file `code.py`, but their *pure* logic (no `Pod`) is unit-testable. Each test loads the function module by path and calls only its pure helpers (no cloud needed — `lemma_sdk` and `pydantic` are installed locally, so import succeeds; we just never call the `Pod`-touching handler).

**Structural validation.** Pod JSON files are JSONC (`//` comments). A shared `tests/jsonc.py` (Task 0) strips comments string-safely so we can `json.loads` them locally before any cloud import.

**Function JSON + grant conventions (CORRECTIONS — verified against the live SDK + platform `permissions.py`; these override the skeleton grants shown in later tasks):**
- Every function `*.json` MUST include `"type": "API"` and `"code": { "$file": "code.py" }` (like `notify_customer.json`).
- Datastore write permission is a single id `datastore.record.write` — there is NO `datastore.record.create`/`.update`. A function that reads+writes a table grants `["datastore.table.read", "datastore.record.read", "datastore.record.write"]`; read-only grants `["datastore.table.read", "datastore.record.read"]`.
- Calling another function from inside a function: use `pod.functions.execute("<fn>", {<input dict>})` (it's an alias of `pod.functions.run`; input is a plain dict). Grant it with `{ "resource_type": "function", "resource_name": "<fn>", "permission_ids": ["function.execute"] }`.
- Sending email via Gmail: the code uses `pod.connectors.execute("workspace-gmail", "gmail_send_email", {...})`, but the GRANT is `{ "resource_type": "connector", "resource_name": "gmail", "permission_ids": ["connector.use"] }` (resource name is `gmail`, not `workspace-gmail`).
- `ResourceType` values are lowercase: `datastore_table`, `function`, `connector`, `folder`.

**Live verification** happens against the live pod (`lemma.work`, org "sahl's Space", pod "An Agetic Helpdesk for Yesmadam Platform Pod"). The cloud CLI session is short-lived — if a `lemma` command returns `INVALID_REFRESH_TOKEN`, ask the user to run `!lemma auth login` (browser, ~60s), then retry. New tables/functions a function touches need `datastore.table.read` + `datastore.record.*` grants or they 403 `MISSING_WORKLOAD_RESOURCE_GRANT`.

---

## Task 0: Repo + test harness scaffold

**Files:**
- Create: `tests/jsonc.py`
- Create: `tests/_load.py`
- Create: `tests/run.sh`

- [ ] **Step 1: Initialise git (skip if user declined)**

Run:
```bash
cd /home/sahl/Documents/lemma/support-desk && git init -q && printf "__pycache__/\n*.pyc\n.venv/\n" > .gitignore
```

- [ ] **Step 2: Create the JSONC parser used by structural tests**

Create `tests/jsonc.py`:
```python
"""Parse JSONC (JSON with // and /* */ comments) string-safely."""
import json


def strip_jsonc(text: str) -> str:
    out, i, n = [], 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1]); i += 2; continue
            if c == '"':
                in_str = False
            i += 1; continue
        if c == '"':
            in_str = True; out.append(c); i += 1; continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2; continue
        out.append(c); i += 1
    return "".join(out)


def load(path: str):
    with open(path) as f:
        return json.loads(strip_jsonc(f.read()))
```

- [ ] **Step 3: Create the function-module loader used by logic tests**

Create `tests/_load.py`:
```python
"""Load a function's code.py by path so its pure helpers can be unit-tested."""
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_fn(function_name: str):
    path = os.path.join(ROOT, "functions", function_name, "code.py")
    spec = importlib.util.spec_from_file_location(f"fn_{function_name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
```

- [ ] **Step 4: Create the test runner**

Create `tests/run.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== py_compile all functions =="
find functions -name code.py -print0 | xargs -0 python3 -m py_compile
echo "== structural + logic tests =="
for t in tests/test_*.py; do echo "-- $t"; python3 "$t"; done
echo "ALL TESTS PASSED"
```

- [ ] **Step 5: Verify the harness runs (no tests yet = passes trivially)**

Run: `bash tests/run.sh`
Expected: `== py_compile all functions ==` then `ALL TESTS PASSED` (the `for` loop matches nothing yet).

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -q -m "chore: test harness (jsonc parser, module loader, runner)"
```

---

## Task 1: Verify the TIME/CRON schedule config shape (de-risk)

**Why first:** the SLA sweeper needs a time-based schedule. `ScheduleType.TIME` + `CRON` mode exist in the SDK; this task pins the exact `config` JSON so Task 10 isn't guesswork, and confirms the lazy-expiry fallback isn't needed.

**Files:** none (investigation only; record findings in the commit message).

- [ ] **Step 1: Inspect an existing TIME schedule's shape from the platform**

Run:
```bash
lemma schedules list 2>&1 | head -40 || true
SDKP=$(python3 -c "import lemma_sdk,os;print(os.path.dirname(lemma_sdk.__file__))")
python3 - "$SDKP" <<'PY'
import json, sys
spec = json.load(open(sys.argv[1] + "/openapi_spec.json"))
schemas = spec["components"]["schemas"]
for name in schemas:
    if "Schedule" in name and ("Create" in name or "Config" in name or "Time" in name):
        print("###", name)
        print(json.dumps(schemas[name], indent=1)[:1200])
PY
```
Expected: a schema (e.g. `CreateScheduleRequest` / a TIME config) revealing the field that carries the cron expression (likely `config.cron_expression` + optional `config.timezone`).

- [ ] **Step 2: Record the confirmed shape**

Write the confirmed TIME-schedule JSON skeleton into the commit message, e.g.:
```
schedule_type "TIME", config { cron_expression: "* * * * *", timezone: "Asia/Kolkata" }, workflow_name, is_active
```
If the platform does NOT support a per-minute TIME schedule, note it — Task 10 then implements lazy expiry instead (sweep overdue rows inside `alert_provider` and `provider_reply` on every run, plus an app-load sweep).

- [ ] **Step 3: Commit the finding**

```bash
git commit -q --allow-empty -m "docs: confirm TIME/CRON schedule config shape for provider-sla (Task 1)"
```

---

## Task 2: Schema migrations

**Files:**
- Create: `tables/provider_responses/provider_responses.json`
- Modify: `tables/bookings/bookings.json` (add `provider_state`)
- Modify: `tables/professionals/professionals.json` (add `contact_email`)
- Modify: `tables/tickets/tickets.json` (add `awaiting_provider` to status enum)
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write the failing structural test**

Create `tests/test_schema.py`:
```python
from tests.jsonc import load
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pr = load("tables/provider_responses/provider_responses.json")
assert pr["name"] == "provider_responses"
cols = {c["name"]: c for c in pr["columns"]}
for c in ["ticket_id", "booking_id", "professional_name", "status",
          "eta_minutes", "proposed_new_time", "alerted_at", "responded_at", "note"]:
    assert c in cols, f"missing column {c}"
assert set(cols["status"]["options"]) == {
    "awaiting", "late", "reschedule", "on_site", "cant_make_it",
    "no_response", "customer_accepted", "customer_declined"}
assert cols["status"]["default"] == "awaiting"

bk = {c["name"]: c for c in load("tables/bookings/bookings.json")["columns"]}
assert bk["provider_state"]["default"] == "idle"
assert set(bk["provider_state"]["options"]) == {"idle", "alerted", "en_route", "stood_down"}

pro = {c["name"]: c for c in load("tables/professionals/professionals.json")["columns"]}
assert "contact_email" in pro

tk = {c["name"]: c for c in load("tables/tickets/tickets.json")["columns"]}
assert "awaiting_provider" in tk["status"]["options"]
print("test_schema OK")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tests/test_schema.py`
Expected: FAIL — `FileNotFoundError` for `provider_responses.json`.

- [ ] **Step 3: Create the `provider_responses` table**

Create `tables/provider_responses/provider_responses.json`:
```jsonc
// provider_responses — one row per provider-coordination event. The professional's
// reply (or the SLA sweeper's timeout) updates `status`, which fires the provider_reply
// workflow. Shared (enable_rls:false) — the ops team and workflows all read/write it.
{
  "name": "provider_responses",
  "primary_key_column": "id",
  "enable_rls": false,
  "columns": [
    { "name": "ticket_id", "type": "UUID", "required": true, "foreign_key": { "references": "tickets.id" },
      "description": "The customer-waiting ticket that triggered the alert" },
    { "name": "booking_id", "type": "UUID", "foreign_key": { "references": "bookings.id" } },
    { "name": "professional_name", "type": "TEXT", "max_length": 160 },
    { "name": "status", "type": "ENUM", "required": true, "default": "awaiting",
      "options": ["awaiting", "late", "reschedule", "on_site", "cant_make_it", "no_response", "customer_accepted", "customer_declined"],
      "description": "awaiting=pinged; late/reschedule/on_site/cant_make_it=pro chose; no_response=SLA expiry; customer_accepted/declined=reschedule offer leg" },
    { "name": "eta_minutes", "type": "INT", "description": "Minutes the pro asked the client to wait (status=late)" },
    { "name": "proposed_new_time", "type": "DATETIME", "description": "Pro's proposed slot (status=reschedule)" },
    { "name": "alerted_at", "type": "DATETIME", "description": "When the pro was alerted — the SLA clock" },
    { "name": "responded_at", "type": "DATETIME", "description": "When the pro/customer last acted" },
    { "name": "note", "type": "TEXT", "max_length": 1900 }
  ],
  "config": {}
}
```

- [ ] **Step 4: Add `provider_state` to `bookings`**

In `tables/bookings/bookings.json`, after the `completion_otp_verified` column object, add:
```jsonc
    ,{ "name": "provider_state", "type": "ENUM", "default": "idle",
      "options": ["idle", "alerted", "en_route", "stood_down"],
      "description": "Coordination lock: alerted=pinged; en_route=committed (blocks refunds); stood_down=out/timed-out (refund/replace allowed)" }
```

- [ ] **Step 5: Add `contact_email` to `professionals`**

In `tables/professionals/professionals.json`, after the `area` column object, add:
```jsonc
    ,{ "name": "contact_email", "type": "TEXT", "max_length": 200,
      "description": "Where the 'client is waiting' alert is sent (Gmail seam; SMS later)" }
```

- [ ] **Step 6: Add `awaiting_provider` to `tickets.status`**

In `tables/tickets/tickets.json`, change the `status` options array to:
```jsonc
      "options": ["new", "triaged", "awaiting_provider", "auto_resolved", "waiting_approval", "escalated", "resolved"],
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `python3 tests/test_schema.py`
Expected: `test_schema OK`

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -q -m "feat(tables): provider_responses + provider_state lock + pro contact_email + awaiting_provider status"
```

---

## Task 3: `verify_service` returns `provider_state`

**Files:**
- Modify: `functions/verify_service/code.py`
- Modify: `functions/verify_service/verify_service.json` (output type + grant already covers bookings.read)
- Test: `tests/test_verify_service.py`

- [ ] **Step 1: Read the current function to match its shape**

Run: `sed -n '1,80p' functions/verify_service/code.py`
Expected: see `VerifyServiceResult` fields (e.g. `service_proven`, `evidence_summary`, `dispute_reason`).

- [ ] **Step 2: Write the failing test (pure: the result model carries provider_state)**

Create `tests/test_verify_service.py`:
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests._load import load_fn

mod = load_fn("verify_service")
fields = mod.VerifyServiceResult.model_fields
assert "provider_state" in fields, "VerifyServiceResult must expose provider_state"
# default must be a safe, non-locking value when no booking
inst = mod.VerifyServiceResult(service_proven=False, provider_state="idle")
assert inst.provider_state == "idle"
print("test_verify_service OK")
```
(If `VerifyServiceResult` has other required fields, set them here to match the real model.)

- [ ] **Step 3: Run it to verify it fails**

Run: `python3 tests/test_verify_service.py`
Expected: FAIL — `AssertionError: ... must expose provider_state`.

- [ ] **Step 4: Add the field + populate it**

In `functions/verify_service/code.py`: add to `VerifyServiceResult`:
```python
    provider_state: str = "idle"
```
In the handler, where the booking is loaded, set it on the result (default `idle` when no booking):
```python
    provider_state = (booking.get("provider_state") or "idle") if booking else "idle"
```
and include `provider_state=provider_state` in the returned `VerifyServiceResult(...)`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `python3 tests/test_verify_service.py`
Expected: `test_verify_service OK`

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -q -m "feat(verify_service): surface booking.provider_state for the gate"
```

---

## Task 4: `notify_provider` function

**Files:**
- Create: `functions/notify_provider/code.py`
- Create: `functions/notify_provider/notify_provider.json`
- Test: `tests/test_notify_provider.py`

- [ ] **Step 1: Write the failing test (pure: the alert body builder)**

Create `tests/test_notify_provider.py`:
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests._load import load_fn

mod = load_fn("notify_provider")
body = mod.build_alert_body(customer_name="Vivaan", service="haircut",
                            address="Koramangala", scheduled="Sat 7:00 pm",
                            sla_minutes=5)
for token in ["Vivaan", "haircut", "Koramangala", "5 minute",
              "running late", "reschedule", "can't make it", "on site"]:
    assert token.lower() in body.lower(), f"alert body missing: {token}"
print("test_notify_provider OK")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tests/test_notify_provider.py`
Expected: FAIL — `ModuleNotFoundError`/`FileNotFoundError` (no `code.py`).

- [ ] **Step 3: Implement the function**

Create `functions/notify_provider/code.py`:
```python
#input_type_name: NotifyProviderInput
#output_type_name: NotifyProviderResult
#function_name: notify_provider

from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod

AUTH_CONFIG = "workspace-gmail"
SEND_OP = "gmail_send_email"


class NotifyProviderInput(BaseModel):
    response_id: str


class NotifyProviderResult(BaseModel):
    sent: bool
    detail: str


def build_alert_body(customer_name: str, service: str, address: str,
                     scheduled: str, sla_minutes: int) -> str:
    return (
        f"Hi — a YesMadam client is waiting on you.\n\n"
        f"Client: {customer_name}\nService: {service}\n"
        f"Where: {address}\nWhen: {scheduled}\n\n"
        f"Please reply within {sla_minutes} minutes with one of:\n"
        f"  1) RUNNING LATE — I'll be there in N minutes\n"
        f"  2) RESCHEDULE — propose a new time\n"
        f"  3) CAN'T MAKE IT today\n"
        f"  4) I'M ON SITE already\n\n"
        f"If we don't hear back in {sla_minutes} minutes we'll resolve it for the client automatically.\n"
        f"— YesMadam Ops"
    )


async def notify_provider(ctx: FunctionContext, data: NotifyProviderInput) -> NotifyProviderResult:
    pod = Pod.from_env()
    resp = pod.table("provider_responses").get(data.response_id)
    booking = pod.table("bookings").get(resp["booking_id"]) if resp.get("booking_id") else {}

    # find the pro's contact email
    pros = pod.records.list("professionals", limit=200).to_dict()["items"]
    pro = next((p for p in pros if (p.get("name") or "").strip().lower()
                == (resp.get("professional_name") or "").strip().lower()), None)
    to_email = (pro or {}).get("contact_email")

    if not to_email:
        pod.records.bulk_create("ticket_events", [{
            "ticket_id": resp["ticket_id"], "kind": "action_taken", "actor": "agent",
            "note": f"Provider alert skipped — no contact_email for {resp.get('professional_name')}"[:1900],
        }])
        return NotifyProviderResult(sent=False, detail="No provider contact email — SLA will resolve.")

    body = build_alert_body(
        customer_name=booking.get("customer_name", "your client"),
        service=booking.get("service", "service"),
        address=booking.get("address", ""),
        scheduled=str(booking.get("scheduled_at", "")),
        sla_minutes=5,
    )
    try:
        pod.connectors.execute(AUTH_CONFIG, SEND_OP, {
            "recipient_email": to_email,
            "subject": f"⏳ Client waiting — booking #{booking.get('code', '')}",
            "body": body,
        })
    except Exception as exc:  # never break coordination over a notification
        pod.records.bulk_create("ticket_events", [{
            "ticket_id": resp["ticket_id"], "kind": "action_taken", "actor": "agent",
            "note": f"Provider alert email failed: {exc}"[:1900],
        }])
        return NotifyProviderResult(sent=False, detail=f"Send failed: {exc}")

    pod.records.bulk_create("ticket_events", [{
        "ticket_id": resp["ticket_id"], "kind": "action_taken", "actor": "agent",
        "note": f"Alerted {resp.get('professional_name')} ({to_email}): client waiting",
    }])
    return NotifyProviderResult(sent=True, detail=f"Alerted {to_email}")
```

Create `functions/notify_provider/notify_provider.json` (grants mirror `notify_customer` + read of `provider_responses`/`professionals`):
```jsonc
{
  "name": "notify_provider",
  "description": "Emails the assigned professional the 'client is waiting' alert with the four response options. Degrades gracefully when no contact email or the send fails.",
  "input_schema": { "type": "object", "properties": { "response_id": { "type": "string" } }, "required": ["response_id"] },
  "output_schema": { "type": "object", "properties": { "sent": { "type": "boolean" }, "detail": { "type": "string" } }, "required": ["sent", "detail"] },
  "permissions": { "grants": [
    { "resource_type": "datastore_table", "resource_name": "provider_responses", "permission_ids": ["datastore.table.read", "datastore.record.read"] },
    { "resource_type": "datastore_table", "resource_name": "bookings", "permission_ids": ["datastore.table.read", "datastore.record.read"] },
    { "resource_type": "datastore_table", "resource_name": "professionals", "permission_ids": ["datastore.table.read", "datastore.record.read"] },
    { "resource_type": "datastore_table", "resource_name": "ticket_events", "permission_ids": ["datastore.table.read", "datastore.record.create"] }
  ] }
}
```
(Confirm the exact grant/permission-id strings against an existing function JSON like `functions/notify_customer/notify_customer.json` before importing.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tests/test_notify_provider.py`
Expected: `test_notify_provider OK`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -q -m "feat(notify_provider): provider alert with 4 options, graceful degrade"
```

---

## Task 5: `alert_provider` function

**Files:**
- Create: `functions/alert_provider/code.py`
- Create: `functions/alert_provider/alert_provider.json`
- Test: `tests/test_alert_provider.py`

- [ ] **Step 1: Write the failing test (pure: holding message + idempotency decision)**

Create `tests/test_alert_provider.py`:
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests._load import load_fn

mod = load_fn("alert_provider")

# holding message tells the customer the pro was messaged + the auto-refund promise
msg = mod.build_holding_reply(pro_name="Pooja", sla_minutes=5)
for token in ["Pooja", "5 minute", "refund"]:
    assert token.lower() in msg.lower(), token

# should_alert: only when the booking is not already in an active coordination state
assert mod.should_alert("idle") is True
assert mod.should_alert("stood_down") is True   # fresh coordination allowed after stand-down
assert mod.should_alert("alerted") is False     # already pinged → link, don't re-alert
assert mod.should_alert("en_route") is False
print("test_alert_provider OK")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tests/test_alert_provider.py`
Expected: FAIL — no `code.py`.

- [ ] **Step 3: Implement the function**

Create `functions/alert_provider/code.py`:
```python
#input_type_name: AlertProviderInput
#output_type_name: AlertProviderResult
#function_name: alert_provider

from datetime import datetime, timezone
from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod

SLA_MINUTES = 5


class AlertProviderInput(BaseModel):
    ticket_id: str
    booking_id: str = ""


class AlertProviderResult(BaseModel):
    ticket_id: str
    response_id: str
    alerted: bool
    detail: str


def build_holding_reply(pro_name: str, sla_minutes: int) -> str:
    return (
        f"Thanks for letting us know. We've messaged your professional"
        f"{(' ' + pro_name) if pro_name else ''} from YesMadam's side and asked them to "
        f"confirm. Please hold ~{sla_minutes} minutes. If we don't hear back, we'll "
        f"refund you automatically — you won't need to chase this."
    )


def should_alert(provider_state: str) -> bool:
    return (provider_state or "idle") not in ("alerted", "en_route")


async def alert_provider(ctx: FunctionContext, data: AlertProviderInput) -> AlertProviderResult:
    pod = Pod.from_env()
    bookings = pod.table("bookings")
    booking = bookings.get(data.booking_id) if data.booking_id else {}
    pro_name = booking.get("professional_name", "") if booking else ""
    state = (booking.get("provider_state") or "idle") if booking else "idle"

    now = datetime.now(timezone.utc).isoformat()

    if booking and not should_alert(state):
        # another waiting ticket already opened coordination — link, don't double-alert
        pod.table("tickets").update(data.ticket_id, {
            "status": "awaiting_provider",
            "draft_reply": build_holding_reply(pro_name, SLA_MINUTES),
        })
        pod.records.bulk_create("ticket_events", [{
            "ticket_id": data.ticket_id, "kind": "action_taken", "actor": "agent",
            "note": f"Linked to existing provider coordination (state={state}); no second alert.",
        }])
        return AlertProviderResult(ticket_id=data.ticket_id, response_id="",
                                   alerted=False, detail="linked to open coordination")

    # open a new coordination row
    created = pod.records.bulk_create("provider_responses", [{
        "ticket_id": data.ticket_id,
        "booking_id": data.booking_id,
        "professional_name": pro_name,
        "status": "awaiting",
        "alerted_at": now,
    }])
    response_id = created.to_dict()["items"][0]["id"]

    if data.booking_id:
        bookings.update(data.booking_id, {"provider_state": "alerted"})

    pod.table("tickets").update(data.ticket_id, {
        "status": "awaiting_provider",
        "draft_reply": build_holding_reply(pro_name, SLA_MINUTES),
    })

    # fire the provider alert email (best effort)
    try:
        pod.functions.execute("notify_provider", {"response_id": response_id})
    except Exception as exc:
        pod.records.bulk_create("ticket_events", [{
            "ticket_id": data.ticket_id, "kind": "action_taken", "actor": "agent",
            "note": f"notify_provider call failed (SLA will still resolve): {exc}"[:1900],
        }])

    return AlertProviderResult(ticket_id=data.ticket_id, response_id=response_id,
                               alerted=True, detail=f"alerted {pro_name or 'provider'}")
```
(Verify `pod.records.bulk_create(...).to_dict()["items"][0]["id"]` and `pod.functions.execute(...)` against the SDK during the live task; if `functions.execute` differs, the workflow can call `notify_provider` as a separate node instead — see Task 6 note.)

Create `functions/alert_provider/alert_provider.json`:
```jsonc
{
  "name": "alert_provider",
  "description": "Opens a provider-coordination row, sets the booking en-route lock to 'alerted', parks the ticket as awaiting_provider with a customer holding reply, and triggers the provider alert. Idempotent across multiple waiting tickets for one booking.",
  "input_schema": { "type": "object", "properties": { "ticket_id": { "type": "string" }, "booking_id": { "type": "string" } }, "required": ["ticket_id"] },
  "output_schema": { "type": "object", "properties": {
    "ticket_id": { "type": "string" }, "response_id": { "type": "string" },
    "alerted": { "type": "boolean" }, "detail": { "type": "string" } },
    "required": ["ticket_id", "response_id", "alerted", "detail"] },
  "permissions": { "grants": [
    { "resource_type": "datastore_table", "resource_name": "provider_responses", "permission_ids": ["datastore.table.read", "datastore.record.read", "datastore.record.create"] },
    { "resource_type": "datastore_table", "resource_name": "bookings", "permission_ids": ["datastore.table.read", "datastore.record.read", "datastore.record.update"] },
    { "resource_type": "datastore_table", "resource_name": "tickets", "permission_ids": ["datastore.table.read", "datastore.record.read", "datastore.record.update"] },
    { "resource_type": "datastore_table", "resource_name": "ticket_events", "permission_ids": ["datastore.table.read", "datastore.record.create"] },
    { "resource_type": "function", "resource_name": "notify_provider", "permission_ids": ["function.execute"] }
  ] }
}
```
(Confirm the `function.execute` grant shape against the platform; if cross-function calls aren't grantable, drop the `pod.functions.execute` and make `notify_provider` a workflow node after `alert_provider` in Task 6.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tests/test_alert_provider.py`
Expected: `test_alert_provider OK`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -q -m "feat(alert_provider): open coordination, set lock, park ticket, fire alert"
```

---

## Task 6: `handle_ticket` — alert branch + refund-lock gate rule

**Files:**
- Modify: `workflows/handle_ticket/handle_ticket.json`
- Test: `tests/test_handle_ticket_graph.py`

- [ ] **Step 1: Write the failing graph test**

Create `tests/test_handle_ticket_graph.py`:
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.jsonc import load

wf = load("workflows/handle_ticket/handle_ticket.json")
nodes = {n["id"]: n for n in wf["nodes"]}
assert "alert_provider" in nodes, "missing alert_provider node"

gate = nodes["gate"]["config"]["rules"]
conds = [r["condition"] for r in gate]
# 1) refund lock now also blocks when pro is committed
assert any("provider_state" in c and "refund" in c for c in conds), "refund lock missing provider_state"
# 2) a rule routes waiting categories to alert_provider
assert any(r["next_node_id"] == "alert_provider" for r in gate), "no rule routes to alert_provider"

# alert_provider must lead to notify->end (customer holding email), not execute_resolution
edges = wf["edges"]
out = [e["target"] for e in edges if e["source"] == "alert_provider"]
assert out and all(t in ("notify", "end") for t in out), f"alert_provider should go to notify/end, got {out}"
print("test_handle_ticket_graph OK")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tests/test_handle_ticket_graph.py`
Expected: FAIL — `missing alert_provider node`.

- [ ] **Step 3: Edit the gate rules**

In `workflows/handle_ticket/handle_ticket.json`, replace the `gate` node's `rules` array with (order matters — refund-lock first, then the alert branch, then auto-resolve):
```jsonc
        "rules": [
          {
            "condition": "triage.proposed_action == 'refund' && (verify_service.service_proven == `true` || verify_service.provider_state == 'alerted' || verify_service.provider_state == 'en_route')",
            "next_node_id": "escalate_form"
          },
          {
            "condition": "(triage.category == 'no_show' || triage.category == 'where_is_pro') && triage.booking_found && verify_service.provider_state != 'stood_down'",
            "next_node_id": "alert_provider"
          },
          {
            "condition": "triage.confidence >= `0.8` && triage.booking_found && triage.refund_amount <= `1500` && (triage.category == 'reschedule' || triage.category == 'cancel_refund' || triage.category == 'no_show' || triage.category == 'where_is_pro')",
            "next_node_id": "execute_auto"
          }
        ]
```

- [ ] **Step 4: Add the `alert_provider` node**

Add to the `nodes` array:
```jsonc
    {
      "id": "alert_provider",
      "type": "FUNCTION",
      "label": "Alert the professional (client waiting)",
      "config": {
        "function_name": "alert_provider",
        "input_mapping": {
          "ticket_id": { "type": "expression", "value": "start.metadata.record_id" },
          "booking_id": { "type": "expression", "value": "triage.booking_id", "optional": true }
        }
      }
    },
```

- [ ] **Step 5: Wire the edges**

Add to the `edges` array:
```jsonc
    { "id": "e_alert1", "source": "gate", "target": "alert_provider", "label": "customer waiting -> alert pro" },
    { "id": "e_alert2", "source": "alert_provider", "target": "notify" },
```
(`notify` emails the customer the holding reply already set on the ticket. If Task 5's in-function `notify_provider` call was dropped, instead insert a `notify_provider` FUNCTION node between `alert_provider` and `notify`.)

- [ ] **Step 6: Run the test + full harness**

Run: `python3 tests/test_handle_ticket_graph.py && bash tests/run.sh`
Expected: `test_handle_ticket_graph OK` … `ALL TESTS PASSED`

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -q -m "feat(handle_ticket): alert-pro branch for waiting tickets + cross-ticket refund lock"
```

---

## Task 7: `stand_down` function

**Files:**
- Create: `functions/stand_down/code.py`
- Create: `functions/stand_down/stand_down.json`
- Test: `tests/test_stand_down.py`

- [ ] **Step 1: Write the failing test (pure: action mapping)**

Create `tests/test_stand_down.py`:
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests._load import load_fn
mod = load_fn("stand_down")
# silence / explicit-out / declined-reschedule all stand down to a resolution attempt
assert mod.resolution_for("no_response") == "assign_replacement"
assert mod.resolution_for("cant_make_it") == "assign_replacement"
assert mod.resolution_for("customer_declined") == "assign_replacement"
print("test_stand_down OK")
```
(Per the spec's judgment call, all stand-down paths funnel through `execute_resolution(assign_replacement)`, which itself falls back to a full refund when no replacement exists.)

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tests/test_stand_down.py`
Expected: FAIL — no `code.py`.

- [ ] **Step 3: Implement the function**

Create `functions/stand_down/code.py`:
```python
#input_type_name: StandDownInput
#output_type_name: StandDownResult
#function_name: stand_down

from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


class StandDownInput(BaseModel):
    response_id: str


class StandDownResult(BaseModel):
    ticket_id: str
    detail: str


def resolution_for(status: str) -> str:
    # One proven path: assign a replacement when possible; execute_resolution falls
    # back to a full refund when no active same-service pro is available.
    return "assign_replacement"


async def stand_down(ctx: FunctionContext, data: StandDownInput) -> StandDownResult:
    pod = Pod.from_env()
    resp = pod.table("provider_responses").get(data.response_id)
    ticket_id = resp["ticket_id"]
    booking_id = resp.get("booking_id") or ""

    # flip the lock so refunds/replacements are allowed again
    if booking_id:
        pod.table("bookings").update(booking_id, {"provider_state": "stood_down"})

    action = resolution_for(resp.get("status") or "no_response")
    pod.functions.execute("execute_resolution", {
        "ticket_id": ticket_id,
        "action": action,
        "booking_id": booking_id,
        "reply": "We couldn't confirm your professional in time, so we've sorted this out for you — details below.",
        "resolution_status": "auto_resolved",
        "actor": "agent",
    })
    pod.records.bulk_create("ticket_events", [{
        "ticket_id": ticket_id, "kind": "action_taken", "actor": "agent",
        "note": f"Stood down (status={resp.get('status')}) -> {action} (refund fallback if no pro).",
    }])
    return StandDownResult(ticket_id=ticket_id, detail=f"stood down -> {action}")
```

Create `functions/stand_down/stand_down.json`:
```jsonc
{
  "name": "stand_down",
  "description": "Releases the en-route lock and resolves the ticket via execute_resolution(assign_replacement), which falls back to a full refund when no replacement is available.",
  "input_schema": { "type": "object", "properties": { "response_id": { "type": "string" } }, "required": ["response_id"] },
  "output_schema": { "type": "object", "properties": { "ticket_id": { "type": "string" }, "detail": { "type": "string" } }, "required": ["ticket_id", "detail"] },
  "permissions": { "grants": [
    { "resource_type": "datastore_table", "resource_name": "provider_responses", "permission_ids": ["datastore.table.read", "datastore.record.read"] },
    { "resource_type": "datastore_table", "resource_name": "bookings", "permission_ids": ["datastore.table.read", "datastore.record.update"] },
    { "resource_type": "datastore_table", "resource_name": "ticket_events", "permission_ids": ["datastore.table.read", "datastore.record.create"] },
    { "resource_type": "function", "resource_name": "execute_resolution", "permission_ids": ["function.execute"] }
  ] }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tests/test_stand_down.py`
Expected: `test_stand_down OK`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -q -m "feat(stand_down): release lock + resolve via replacement/refund fallback"
```

---

## Task 8: `provider_reply` workflow + functions for `late` / `on_site` / reschedule

> **CORRECTION (verified against platform):** the workflow start context exposes only
> `start.payload.*` and `start.metadata.*` (record_id) — there is NO `start.record.*`,
> and an UPDATE's `payload` is just the changed-field delta. So the workflow must NOT
> route on `start.record.status`. Instead a new **`read_response`** function (input
> `response_id` = `start.metadata.record_id`) fetches the full `provider_responses` row
> PLUS the booking's `provider_state`/`status`, and the guard/route DECISIONS read from
> `read_response.*`. This replaces the `verify_service` "load" node. Split into **8a**
> (the route functions incl. `read_response`) and **8b** (the workflow wiring).

**Files:**
- Create: `functions/commit_en_route/code.py` + `.json` (handles `late` and `on_site`)
- Create: `functions/offer_reschedule/code.py` + `.json`
- Create: `functions/apply_reschedule/code.py` + `.json`
- Create: `functions/provider_stand_notice/code.py` + `.json` (late-reply no-op notice)
- Create: `workflows/provider_reply/provider_reply.json`
- Test: `tests/test_provider_reply.py`

- [ ] **Step 1: Write the failing routing + graph test**

Create `tests/test_provider_reply.py`:
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.jsonc import load
from tests._load import load_fn

wf = load("workflows/provider_reply/provider_reply.json")
assert wf["start"]["type"] == "DATASTORE_EVENT"
assert wf["start"]["config"]["table_name"] == "provider_responses"
assert wf["start"]["config"]["operations"] == ["UPDATE"]
nodes = {n["id"] for n in wf["nodes"]}
for n in ["guard", "route", "commit_en_route", "offer_reschedule",
          "apply_reschedule", "stand_down", "provider_stand_notice"]:
    assert n in nodes, f"missing node {n}"

route = next(n for n in wf["nodes"] if n["id"] == "route")["config"]["rules"]
targets = {r["next_node_id"] for r in route}
assert {"commit_en_route", "offer_reschedule", "apply_reschedule", "stand_down"} <= targets

# pure: en-route reply builder mentions ETA
cer = load_fn("commit_en_route")
r = cer.build_customer_reply(pro_name="Karan", eta_minutes=15, on_site=False)
assert "Karan" in r and "15" in r
r2 = cer.build_customer_reply(pro_name="Karan", eta_minutes=0, on_site=True)
assert "on" in r2.lower()
print("test_provider_reply OK")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tests/test_provider_reply.py`
Expected: FAIL — workflow file not found.

- [ ] **Step 3: Implement `commit_en_route`**

Create `functions/commit_en_route/code.py`:
```python
#input_type_name: CommitEnRouteInput
#output_type_name: CommitEnRouteResult
#function_name: commit_en_route

from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


class CommitEnRouteInput(BaseModel):
    response_id: str


class CommitEnRouteResult(BaseModel):
    ticket_id: str
    detail: str


def build_customer_reply(pro_name: str, eta_minutes: int, on_site: bool) -> str:
    who = pro_name or "your professional"
    if on_site:
        return (f"Good news — {who} reports they're already on site for your appointment. "
                f"If that's not what you're seeing, reply and we'll jump in.")
    return (f"Good news — {who} is on the way and should reach you in about "
            f"{eta_minutes} minutes. Thanks for your patience!")


async def commit_en_route(ctx: FunctionContext, data: CommitEnRouteInput) -> CommitEnRouteResult:
    pod = Pod.from_env()
    resp = pod.table("provider_responses").get(data.response_id)
    ticket_id = resp["ticket_id"]
    booking_id = resp.get("booking_id") or ""
    on_site = (resp.get("status") == "on_site")
    eta = int(resp.get("eta_minutes") or 0)
    pro = resp.get("professional_name", "")

    if booking_id:
        pod.table("bookings").update(booking_id, {
            "provider_state": "en_route",
            "last_action": ("Pro reports on-site" if on_site else f"Pro en route, ETA {eta}m"),
        })

    reply = build_customer_reply(pro, eta, on_site)
    # on_site is a likely false complaint -> park for a human with the proof note;
    # otherwise the ETA reply auto-resolves the waiting ticket.
    ticket_status = "waiting_approval" if on_site else "auto_resolved"
    pod.table("tickets").update(ticket_id, {"status": ticket_status, "draft_reply": reply})
    pod.records.bulk_create("ticket_events", [{
        "ticket_id": ticket_id, "kind": "action_taken", "actor": "agent",
        "note": ("On-site claim — parked for human + proof-of-service" if on_site
                 else f"Pro en route, ETA {eta}m; customer reassured"),
    }])
    if not on_site:
        pod.functions.execute("notify_customer", {"ticket_id": ticket_id})
    return CommitEnRouteResult(ticket_id=ticket_id, detail=("on_site->human" if on_site else "en_route"))
```

Create `functions/commit_en_route/commit_en_route.json`:
```jsonc
{
  "name": "commit_en_route",
  "description": "Pro is coming (late) or claims on-site: sets the en_route lock, reassures the customer (late) or parks for human review (on_site).",
  "input_schema": { "type": "object", "properties": { "response_id": { "type": "string" } }, "required": ["response_id"] },
  "output_schema": { "type": "object", "properties": { "ticket_id": { "type": "string" }, "detail": { "type": "string" } }, "required": ["ticket_id", "detail"] },
  "permissions": { "grants": [
    { "resource_type": "datastore_table", "resource_name": "provider_responses", "permission_ids": ["datastore.table.read", "datastore.record.read"] },
    { "resource_type": "datastore_table", "resource_name": "bookings", "permission_ids": ["datastore.table.read", "datastore.record.update"] },
    { "resource_type": "datastore_table", "resource_name": "tickets", "permission_ids": ["datastore.table.read", "datastore.record.update"] },
    { "resource_type": "datastore_table", "resource_name": "ticket_events", "permission_ids": ["datastore.table.read", "datastore.record.create"] },
    { "resource_type": "function", "resource_name": "notify_customer", "permission_ids": ["function.execute"] }
  ] }
}
```

- [ ] **Step 4: Implement `offer_reschedule`**

Create `functions/offer_reschedule/code.py`:
```python
#input_type_name: OfferRescheduleInput
#output_type_name: OfferRescheduleResult
#function_name: offer_reschedule

from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


class OfferRescheduleInput(BaseModel):
    response_id: str


class OfferRescheduleResult(BaseModel):
    ticket_id: str
    detail: str


def build_offer_reply(pro_name: str, new_time: str) -> str:
    who = pro_name or "Your professional"
    return (f"{who} can't make the original slot but offers to come at {new_time} instead. "
            f"Reply YES to confirm, or NO and we'll cancel and refund you.")


async def offer_reschedule(ctx: FunctionContext, data: OfferRescheduleInput) -> OfferRescheduleResult:
    pod = Pod.from_env()
    resp = pod.table("provider_responses").get(data.response_id)
    ticket_id = resp["ticket_id"]
    booking_id = resp.get("booking_id") or ""
    new_time = str(resp.get("proposed_new_time") or "")
    pro = resp.get("professional_name", "")

    # hold: pro is committed to the new time pending customer's YES/NO
    if booking_id:
        pod.table("bookings").update(booking_id, {
            "provider_state": "en_route",
            "last_action": f"Reschedule offered to {new_time} (awaiting customer)",
        })
    reply = build_offer_reply(pro, new_time)
    pod.table("tickets").update(ticket_id, {"status": "awaiting_provider", "draft_reply": reply})
    pod.functions.execute("notify_customer", {"ticket_id": ticket_id})
    pod.records.bulk_create("ticket_events", [{
        "ticket_id": ticket_id, "kind": "action_taken", "actor": "agent",
        "note": f"Reschedule offer sent: {new_time}",
    }])
    return OfferRescheduleResult(ticket_id=ticket_id, detail=f"offered {new_time}")
```

Create `functions/offer_reschedule/offer_reschedule.json` (same grant set as `commit_en_route`, with the name/description updated).

- [ ] **Step 5: Implement `apply_reschedule`**

Create `functions/apply_reschedule/code.py`:
```python
#input_type_name: ApplyRescheduleInput
#output_type_name: ApplyRescheduleResult
#function_name: apply_reschedule

from datetime import datetime, timezone
from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


class ApplyRescheduleInput(BaseModel):
    response_id: str


class ApplyRescheduleResult(BaseModel):
    ticket_id: str
    detail: str


def is_valid_future(new_time_iso: str, now_iso: str) -> bool:
    try:
        nt = datetime.fromisoformat(new_time_iso.replace("Z", "+00:00"))
        now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        return nt > now
    except Exception:
        return False


async def apply_reschedule(ctx: FunctionContext, data: ApplyRescheduleInput) -> ApplyRescheduleResult:
    pod = Pod.from_env()
    resp = pod.table("provider_responses").get(data.response_id)
    ticket_id = resp["ticket_id"]
    booking_id = resp.get("booking_id") or ""
    new_time = str(resp.get("proposed_new_time") or "")
    now = datetime.now(timezone.utc).isoformat()

    if not booking_id or not is_valid_future(new_time, now):
        # invalid offer -> safest is to stand down (refund/replacement)
        pod.functions.execute("stand_down", {"response_id": data.response_id})
        return ApplyRescheduleResult(ticket_id=ticket_id, detail="invalid new_time -> stand_down")

    if booking_id:
        pod.table("bookings").update(booking_id, {"provider_state": "en_route"})
    pod.functions.execute("execute_resolution", {
        "ticket_id": ticket_id,
        "action": "reschedule",
        "booking_id": booking_id,
        "proposed_new_time": new_time,
        "reply": f"Confirmed — your appointment is now at {new_time}. See you then!",
        "resolution_status": "auto_resolved",
        "actor": "agent",
    })
    return ApplyRescheduleResult(ticket_id=ticket_id, detail=f"rescheduled to {new_time}")
```

Create `functions/apply_reschedule/apply_reschedule.json` (grants: bookings.update, function.execute on `execute_resolution` and `stand_down`, provider_responses.read).

- [ ] **Step 6: Implement `provider_stand_notice` (late-reply no-op)**

Create `functions/provider_stand_notice/code.py`:
```python
#input_type_name: ProviderStandNoticeInput
#output_type_name: ProviderStandNoticeResult
#function_name: provider_stand_notice

from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


class ProviderStandNoticeInput(BaseModel):
    response_id: str


class ProviderStandNoticeResult(BaseModel):
    detail: str


async def provider_stand_notice(ctx: FunctionContext, data: ProviderStandNoticeInput) -> ProviderStandNoticeResult:
    pod = Pod.from_env()
    resp = pod.table("provider_responses").get(data.response_id)
    pod.records.bulk_create("ticket_events", [{
        "ticket_id": resp["ticket_id"], "kind": "action_taken", "actor": "agent",
        "note": f"Late provider reply ignored — booking already resolved (status={resp.get('status')}).",
    }])
    return ProviderStandNoticeResult(detail="late reply ignored")
```
Create `functions/provider_stand_notice/provider_stand_notice.json` (grants: provider_responses.read, ticket_events.create).

- [ ] **Step 7: Implement the `provider_reply` workflow**

Create `workflows/provider_reply/provider_reply.json`:
```jsonc
{
  "name": "provider_reply",
  "description": "Fires when a provider_responses row's status changes. Routes the professional's choice (late/on_site/reschedule/cant_make_it), the customer's reschedule YES/NO, or an SLA timeout into the right booking action. Read-only on provider_responses (never writes it) to avoid event loops.",
  "start": { "type": "DATASTORE_EVENT", "config": { "table_name": "provider_responses", "operations": ["UPDATE"] } },
  "nodes": [
    {
      "id": "load",
      "type": "FUNCTION",
      "label": "Load coordination + booking state",
      "config": {
        "function_name": "verify_service",
        "input_mapping": { "booking_id": { "type": "expression", "value": "start.record.booking_id", "optional": true } }
      }
    },
    {
      "id": "guard",
      "type": "DECISION",
      "label": "Already resolved / late reply?",
      "config": {
        "rules": [
          { "condition": "verify_service.provider_state == 'stood_down'", "next_node_id": "provider_stand_notice" }
        ]
      }
    },
    {
      "id": "route",
      "type": "DECISION",
      "label": "Route the provider/customer decision",
      "config": {
        "rules": [
          { "condition": "start.record.status == 'late' || start.record.status == 'on_site'", "next_node_id": "commit_en_route" },
          { "condition": "start.record.status == 'reschedule'", "next_node_id": "offer_reschedule" },
          { "condition": "start.record.status == 'customer_accepted'", "next_node_id": "apply_reschedule" },
          { "condition": "start.record.status == 'cant_make_it' || start.record.status == 'no_response' || start.record.status == 'customer_declined'", "next_node_id": "stand_down" }
        ]
      }
    },
    { "id": "commit_en_route", "type": "FUNCTION", "label": "Pro coming / on-site",
      "config": { "function_name": "commit_en_route", "input_mapping": { "response_id": { "type": "expression", "value": "start.metadata.record_id" } } } },
    { "id": "offer_reschedule", "type": "FUNCTION", "label": "Offer new time to customer",
      "config": { "function_name": "offer_reschedule", "input_mapping": { "response_id": { "type": "expression", "value": "start.metadata.record_id" } } } },
    { "id": "apply_reschedule", "type": "FUNCTION", "label": "Customer accepted -> reschedule",
      "config": { "function_name": "apply_reschedule", "input_mapping": { "response_id": { "type": "expression", "value": "start.metadata.record_id" } } } },
    { "id": "stand_down", "type": "FUNCTION", "label": "Stand down -> replacement/refund",
      "config": { "function_name": "stand_down", "input_mapping": { "response_id": { "type": "expression", "value": "start.metadata.record_id" } } } },
    { "id": "provider_stand_notice", "type": "FUNCTION", "label": "Late reply (no-op)",
      "config": { "function_name": "provider_stand_notice", "input_mapping": { "response_id": { "type": "expression", "value": "start.metadata.record_id" } } } },
    { "id": "end", "type": "END", "label": "Done" }
  ],
  "edges": [
    { "id": "p1", "source": "load", "target": "guard" },
    { "id": "p2", "source": "guard", "target": "route", "label": "not yet resolved (default)" },
    { "id": "p3", "source": "guard", "target": "provider_stand_notice", "label": "already stood down" },
    { "id": "p4", "source": "route", "target": "commit_en_route", "label": "late/on_site" },
    { "id": "p5", "source": "route", "target": "offer_reschedule", "label": "reschedule" },
    { "id": "p6", "source": "route", "target": "apply_reschedule", "label": "customer accepted" },
    { "id": "p7", "source": "route", "target": "stand_down", "label": "cant/no_response/declined" },
    { "id": "p8", "source": "commit_en_route", "target": "end" },
    { "id": "p9", "source": "offer_reschedule", "target": "end" },
    { "id": "p10", "source": "apply_reschedule", "target": "end" },
    { "id": "p11", "source": "stand_down", "target": "end" },
    { "id": "p12", "source": "provider_stand_notice", "target": "end" }
  ]
}
```
(Verify the event payload path for the changed row — `start.record.status` / `start.metadata.record_id` — against an existing workflow's `start.*` usage during the live task; `handle_ticket` uses `start.metadata.record_id`. If `start.record.*` isn't available, the route DECISION can read the status via the `load`/verify_service output instead, or add a tiny `read_response` function that returns the row.)

- [ ] **Step 8: Run the test + full harness**

Run: `python3 tests/test_provider_reply.py && bash tests/run.sh`
Expected: `test_provider_reply OK` … `ALL TESTS PASSED`

- [ ] **Step 9: Commit**

```bash
git add -A && git commit -q -m "feat(provider_reply): workflow + commit_en_route/offer/apply_reschedule/stand_notice"
```

---

## Task 9: `sweep_provider_sla` function + `provider-sla` schedule

**Files:**
- Create: `functions/sweep_provider_sla/code.py` + `.json`
- Create: `workflows/sweep_sla/sweep_sla.json` (one-node cron wrapper — schedules target a workflow)
- Create: `schedules/provider-sla/provider-sla.json`
- Test: `tests/test_sweep_sla.py`

- [ ] **Step 1: Write the failing test (pure: expiry decision)**

Create `tests/test_sweep_sla.py`:
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests._load import load_fn
mod = load_fn("sweep_provider_sla")
# awaiting + older than SLA -> expire to no_response
assert mod.next_status("awaiting", minutes_elapsed=6, sla=5) == "no_response"
# reschedule offer with no customer reply past SLA -> declined
assert mod.next_status("reschedule", minutes_elapsed=6, sla=5) == "customer_declined"
# still within SLA -> no change
assert mod.next_status("awaiting", minutes_elapsed=2, sla=5) is None
# already-decided rows -> never swept
assert mod.next_status("late", minutes_elapsed=99, sla=5) is None
print("test_sweep_sla OK")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tests/test_sweep_sla.py`
Expected: FAIL — no `code.py`.

- [ ] **Step 3: Implement the function**

Create `functions/sweep_provider_sla/code.py`:
```python
#input_type_name: SweepProviderSlaInput
#output_type_name: SweepProviderSlaResult
#function_name: sweep_provider_sla

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod

SLA_MINUTES = 5


class SweepProviderSlaInput(BaseModel):
    pass


class SweepProviderSlaResult(BaseModel):
    swept: int
    detail: str


def next_status(status: str, minutes_elapsed: float, sla: int) -> Optional[str]:
    if minutes_elapsed < sla:
        return None
    if status == "awaiting":
        return "no_response"
    if status == "reschedule":
        return "customer_declined"
    return None


def _elapsed_minutes(alerted_at: str, now: datetime) -> float:
    try:
        t = datetime.fromisoformat((alerted_at or "").replace("Z", "+00:00"))
        return (now - t).total_seconds() / 60.0
    except Exception:
        return 0.0


async def sweep_provider_sla(ctx: FunctionContext, data: SweepProviderSlaInput) -> SweepProviderSlaResult:
    pod = Pod.from_env()
    now = datetime.now(timezone.utc)
    rows = pod.records.list("provider_responses", limit=500).to_dict()["items"]
    swept = 0
    for r in rows:
        nxt = next_status(r.get("status") or "", _elapsed_minutes(r.get("alerted_at"), now), SLA_MINUTES)
        if nxt:
            pod.table("provider_responses").update(r["id"], {
                "status": nxt, "responded_at": now.isoformat(),
                "note": ((r.get("note") or "") + f" | SLA expiry -> {nxt}")[:1900],
            })
            swept += 1
    return SweepProviderSlaResult(swept=swept, detail=f"expired {swept} row(s)")
```
(Note: this UPDATE is what fires `provider_reply` for timed-out rows — exactly the external-actor pattern the design relies on.)

Create `functions/sweep_provider_sla/sweep_provider_sla.json` (grants: provider_responses.read + provider_responses.update).

- [ ] **Step 4: Create the one-node sweeper workflow (schedules target a workflow, not a bare function — confirmed in Task 1)**

Create `workflows/sweep_sla/sweep_sla.json`:
```jsonc
// Cron-driven wrapper so the TIME schedule has a workflow to fire (pod schedules
// target agent_name or workflow_name, never a bare function — confirmed Task 1).
{
  "name": "sweep_sla",
  "description": "Every minute: expire provider_responses rows past the 5-minute SLA (awaiting -> no_response, reschedule offer -> customer_declined), which fires provider_reply to resolve the customer.",
  "start": { "type": "SCHEDULED", "config": { "schedule_type": "CRON" } },
  "nodes": [
    { "id": "sweep", "type": "FUNCTION", "label": "Sweep overdue coordination rows",
      "config": { "function_name": "sweep_provider_sla", "input_mapping": {} } },
    { "id": "end", "type": "END", "label": "Done" }
  ],
  "edges": [ { "id": "s1", "source": "sweep", "target": "end" } ]
}
```

- [ ] **Step 5: Create the TIME schedule (confirmed shape: `schedule_type: "TIME"`, `config.cron`, `workflow_name`)**

Create `schedules/provider-sla/provider-sla.json`:
```jsonc
// Time-based sweep: every minute, fire sweep_sla to expire overdue coordination rows.
// Confirmed Task 1: TimeScheduleConfig uses {"cron": "<expr>"}; schedule targets a workflow.
{
  "name": "provider-sla",
  "schedule_type": "TIME",
  "config": { "cron": "* * * * *" },
  "workflow_name": "sweep_sla",
  "is_active": true
}
```
(Renumber the remaining steps in this task accordingly. The original `function_name`-targeted schedule shape is wrong — schedules require exactly one of `agent_name`/`workflow_name`.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `python3 tests/test_sweep_sla.py`
Expected: `test_sweep_sla OK`

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -q -m "feat(sla): sweep_provider_sla + provider-sla schedule (5-min timeout -> auto resolve)"
```

---

## Task 10: Seed data — pro emails, waiting scenario, reply simulator, race case

**Files:**
- Modify: `seed/seed.sh`
- Create: `seed/simulate_provider_reply.sh`
- Test: `tests/test_seed_parse.py`

- [ ] **Step 1: Read the current seed to match its CLI idioms**

Run: `sed -n '1,60p' seed/seed.sh`
Expected: see how rows are inserted (the `lemma` record-create commands / payloads).

- [ ] **Step 2: Write the failing test (seed mentions the new fields + simulator exists)**

Create `tests/test_seed_parse.py`:
```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
seed = open("seed/seed.sh").read()
assert "contact_email" in seed, "seed must set provider contact_email"
assert os.path.exists("seed/simulate_provider_reply.sh"), "missing provider-reply simulator"
sim = open("seed/simulate_provider_reply.sh").read()
for opt in ["late", "reschedule", "cant_make_it", "on_site"]:
    assert opt in sim, f"simulator missing option {opt}"
print("test_seed_parse OK")
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python3 tests/test_seed_parse.py`
Expected: FAIL — `seed must set provider contact_email`.

- [ ] **Step 4: Add `contact_email` to seeded pros + a waiting scenario + a race case**

In `seed/seed.sh`, following its existing record-create idiom: (a) add `contact_email` (use the user's own address `9429.sahl@gmail.com` so the alert actually sends once Gmail is connected) to each professional insert; (b) add a fresh `no_show`/`where_is_pro` ticket on a `scheduled` booking whose pro has a contact email (the waiting scenario); (c) add a booking with `provider_state` `en_route` plus an incoming `cancel_refund` ticket on it (the cross-ticket race case the refund-lock must catch).

- [ ] **Step 5: Create the provider-reply simulator**

Create `seed/simulate_provider_reply.sh`:
```bash
#!/usr/bin/env bash
# Simulate a professional's reply by updating their open provider_responses row.
# Usage: ./simulate_provider_reply.sh <response_id> <late|reschedule|cant_make_it|on_site> [eta_or_isotime]
set -euo pipefail
RID="$1"; CHOICE="$2"; ARG="${3:-}"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
case "$CHOICE" in
  late)         FIELDS="{\"status\":\"late\",\"eta_minutes\":${ARG:-15},\"responded_at\":\"$NOW\"}";;
  reschedule)   FIELDS="{\"status\":\"reschedule\",\"proposed_new_time\":\"${ARG}\",\"responded_at\":\"$NOW\"}";;
  cant_make_it) FIELDS="{\"status\":\"cant_make_it\",\"responded_at\":\"$NOW\"}";;
  on_site)      FIELDS="{\"status\":\"on_site\",\"responded_at\":\"$NOW\"}";;
  *) echo "unknown choice: $CHOICE"; exit 1;;
esac
echo "Updating provider_responses/$RID -> $FIELDS"
# Replace with the project's actual record-update CLI/SDK call (match seed.sh idiom):
lemma records update provider_responses "$RID" --data "$FIELDS"
```
(Match the exact `lemma records update ...` invocation to whatever `seed.sh` uses for writes; adjust if the project uses a Python SDK script instead.)

- [ ] **Step 6: Run the test to verify it passes**

Run: `python3 tests/test_seed_parse.py && bash -n seed/seed.sh && bash -n seed/simulate_provider_reply.sh`
Expected: `test_seed_parse OK` and no bash syntax errors.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -q -m "feat(seed): pro emails, waiting scenario, race case, provider-reply simulator"
```

---

## Task 11: Ops-queue app — surface awaiting_provider + en-route lock

**Files:**
- Modify: `apps/ops-queue/html.html`
- Test: manual (visual) + `tests/test_app_strings.py`

- [ ] **Step 1: Write the failing string test**

Create `tests/test_app_strings.py`:
```python
html = open("apps/ops-queue/html.html").read()
assert "awaiting_provider" in html, "app must render the awaiting_provider status"
assert "provider_state" in html or "en_route" in html, "app must show the en-route lock"
print("test_app_strings OK")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tests/test_app_strings.py`
Expected: FAIL.

- [ ] **Step 3: Add the UI**

In `apps/ops-queue/html.html`, following its existing status-badge and booking-render code: (a) add an `awaiting_provider` badge ("Pro messaged") and, when a ticket is `awaiting_provider`, show the linked `provider_responses` row (status + `alerted_at`, with a simple "N min left" computed against 5 min); (b) add an en-route lock badge on bookings whose `provider_state` is `alerted`/`en_route`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tests/test_app_strings.py`
Expected: `test_app_strings OK`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -q -m "feat(app): surface awaiting_provider + en-route lock in ops-queue"
```

---

## Task 12: Live import + end-to-end verification on the cloud pod

**Files:** none (verification). If a write/field/grant differs from the SDK reality, fix the offending file and re-run that task's local test before re-importing.

- [ ] **Step 1: Ensure CLI session is valid**

Run: `lemma whoami 2>&1 | tail -2`
If `INVALID_REFRESH_TOKEN`: ask the user to run `!lemma auth login` (browser, ~60s), then retry.

- [ ] **Step 2: Import the pod**

Run: `lemma pods import ./ 2>&1 | tail -40`
Expected: success; new resources (`provider_responses`, `alert_provider`, `notify_provider`, `stand_down`, `commit_en_route`, `offer_reschedule`, `apply_reschedule`, `provider_stand_notice`, `sweep_provider_sla`, `provider_reply`, `provider-sla`) created. On `MISSING_WORKLOAD_RESOURCE_GRANT`, add the missing `datastore.table.read`/`record.*` grant to that function's JSON and re-import.

- [ ] **Step 3: Seed the waiting scenario**

Run: `bash seed/seed.sh 2>&1 | tail -20`
Expected: the new `no_show`/`where_is_pro` ticket created; `handle_ticket` fires → the ticket lands `awaiting_provider`, the booking goes `provider_state=alerted`, and a `provider_responses` row exists (`awaiting`). Verify:
```bash
lemma records list tickets --limit 5 2>&1 | tail
lemma records list provider_responses --limit 5 2>&1 | tail
```

- [ ] **Step 4: Verify each provider reply branch**

For the open `provider_responses` row id `<RID>`:
- `late`: `bash seed/simulate_provider_reply.sh <RID> late 15` → booking `provider_state=en_route`, ticket `auto_resolved`, customer reply mentions "15 minutes". 
- `reschedule` → customer YES: `... <RID> reschedule 2026-06-30T18:00:00Z`, then update the same row to `customer_accepted` → booking `rescheduled` to that time, ticket resolved.
- `reschedule` → customer NO: update to `customer_declined` → `stand_down` → replacement assigned or full refund.
- `cant_make_it`: → `stand_down` → replacement/refund.
- `on_site`: → booking `en_route`, ticket `waiting_approval` with proof-of-service note.
Each: re-open a fresh waiting ticket between checks (or reset the booking `provider_state` to `idle`) so coordination starts clean.

- [ ] **Step 5: Verify the SLA timeout path**

Open a fresh waiting ticket, do NOT simulate a reply, wait >5 min (or invoke `sweep_provider_sla` directly: `lemma functions run sweep_provider_sla --data '{}'`). Expected: the `awaiting` row flips to `no_response`, `provider_reply` fires → `stand_down` → customer refunded/replaced; ticket resolved.

- [ ] **Step 6: Verify the cross-ticket race guard**

With the seeded `en_route` booking, confirm its incoming `cancel_refund` ticket did NOT auto-refund — it parked at `waiting_approval` (the human form), because the gate's refund-lock rule matched `provider_state == 'en_route'`. Check `lemma records list tickets` for that ticket's status.

- [ ] **Step 7: Verify the late-reply no-op**

After a booking is `stood_down`/resolved, simulate a `late` reply on its (now stale) response row → `provider_reply` guard routes to `provider_stand_notice`; a `ticket_events` row logs "Late provider reply ignored"; booking unchanged.

- [ ] **Step 8: Final commit + update memory**

```bash
git add -A && git commit -q -m "test: live end-to-end verification of provider coordination loop"
```
Then update `~/.claude/.../memory/yesmadam-support-desk-live.md` with the new loop (tables/functions/workflow/schedule, the en-route lock, the 5-min SLA) so future sessions know it exists.

---

## Self-review notes (for the implementer)

- **Spec coverage:** every spec component (new table, 3 column adds, `verify_service` field, `alert_provider`, `notify_provider`, `stand_down`, `provider_reply` workflow, `sweep_provider_sla` + schedule, gate refund-lock, reschedule sub-loop both legs, app, seed, all edge cases) maps to Tasks 2–12.
- **The two platform unknowns** (exact TIME-schedule `config` fields; the workflow event payload path `start.record.*` for the changed row) are each isolated to one task with a written fallback (lazy expiry; a `read_response` helper). Neither blocks the rest of the build.
- **Anti-fragility invariant** (`provider_reply` never writes `provider_responses`) is preserved: every status transition is written by `alert_provider` (INSERT only, doesn't trigger the UPDATE workflow), the simulator/real pro reply, the customer reply, or the SLA sweeper — never by `provider_reply` itself.
- **`function.execute` grants and cross-function calls** (`pod.functions.execute`) are used in several functions; if the platform doesn't support function-to-function calls, the fallback (stated in Tasks 5, 7, 8) is to promote those calls to explicit workflow nodes.
