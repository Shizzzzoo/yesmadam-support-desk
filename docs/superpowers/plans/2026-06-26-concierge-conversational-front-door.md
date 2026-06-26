# Concierge — Conversational Customer Front Door — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a conversational customer front door — a multi-turn `concierge` agent + a `customer-chat` pod App — that answers questions from booking data, asks clarifying questions, files a clean ticket into the existing `handle_ticket` engine to take the real action, and reads the engine's outcome back to the customer. Concierge never moves money itself.

**Architecture:** Purely additive on the live pod. A read-only conversational agent (`concierge`, toolsets `POD` + `USER_INTERACTION`) calls one mutating function (`file_ticket`) that inserts a `tickets` row; the unchanged `new-ticket` schedule → `handle_ticket` engine resolves it within its existing gates; concierge reads `ticket.status` + `draft_reply` back. The chat UI is a single-file pod App using the authenticated browser `LemmaClient`.

**Tech Stack:** Lemma pod bundle (JSONC + Python `code.py` + single-file HTML app), `lemma` CLI, Python 3.11 + pydantic. Spec: `docs/superpowers/specs/2026-06-26-concierge-conversational-front-door-design.md`.

---

## Conventions (reused from the existing bundle)

**Working dir:** `/home/sahl/Documents/lemma/support-desk` (a git repo; commit per task).

**Test harness already exists:** `tests/run.sh` (py_compile all functions + run every `tests/test_*.py`), `tests/jsonc.py` (`load()` parses JSONC), `tests/_load.py` (`load_fn()` imports a function's `code.py`). Every test file starts with `sys.path.insert(0, <bundle root>)` BEFORE any `tests.*` import.

**Verified function conventions:** function JSON needs `"type": "API"` + `"code": {"$file": "code.py"}`, NO `input_schema`/`output_schema`; write perm id is `datastore.record.write`; `pod.records.create("<table>", {...})` returns the row incl. `["id"]`; cross-fn/grant `{ "resource_type":"function", "resource_name":"X", "permission_ids":["function.execute"] }`.

**Agent bundle shape** (from `lemma agent schema`): `{ name, description, instruction:{"$file":"instruction.md"}, toolsets:[...], visibility, permissions:{grants:[...]} }`. Toolsets include `POD` (read/act on pod data) and `USER_INTERACTION` (the `ask_user` clarifying-question tool). Conversational agents have NO `output_schema`. Agents have zero access by default — grant every table/folder/function touched.

**App bundle shape:** `apps/<name>/<name>.json` = `{ name, description, public_slug }` + `apps/<name>/html.html` (single file; the importer bundles it). `public_slug` → `<slug>.apps.lemma.work`.

**Live runtime:** the conversational agent needs the agent runtime up — start the free daemon with `lemma daemon start` (tracked background process) before live tests. CLI session is short-lived; on `INVALID_REFRESH_TOKEN` ask the user to run `!lemma auth login`.

---

## Task 1: Verify the browser conversation transport (de-risk)

**Why first:** the chat App (Task 4) must drive an agent conversation from the browser `LemmaClient`. Confirm the exact call so Task 4 isn't guesswork.

> **CONFIRMED (verified against the served SDK `api.lemma.work/public/sdk/lemma-client.js`, 200/589KB):**
> - SDK is **first-party**: load `base + "/public/sdk/lemma-client.js"` (base = `window.__LEMMA_CONFIG__.apiUrl || location.origin`), exactly as `ops-queue` does — same-origin, **no CDN / no SRI concern**.
> - Multi-turn API: `const ns = client.conversations();` → `const conv = await ns.createForAgent("concierge", {title})` ONCE → per turn `await ns.messages.send(conv.id, {content})` or streaming `ns.sendMessageStream(conv.id, {content}, {signal})`.
> - **Do NOT use `client.agents.run(...)`** for the chat — its body calls `conversations.createForAgent` every time, starting a fresh conversation (breaks multi-turn context).
> - REST equivalents exist as a fallback: `POST/GET /pods/{pod_id}/conversations`, `.../{id}/messages`, `.../{id}/stream`, `.../{id}/approvals`.
>
> Task 4's `html.html` already uses this confirmed pattern. Remaining best-effort (confirm live in Task 5): the stream event field name and `messages.list` return shape.

**Files:** none (investigation; record the confirmed call in the commit message).

- [ ] **Step 1: Inspect the browser SDK surface + the REST shape**

Run:
```bash
# what methods does the browser client expose? (served SDK + openapi)
SDKP=$(python3 -c "import lemma_sdk,os;print(os.path.dirname(lemma_sdk.__file__))")
python3 - "$SDKP" <<'PY'
import json, sys
spec = json.load(open(sys.argv[1] + "/openapi_spec.json"))
for p in spec.get("paths", {}):
    if "conversation" in p.lower():
        print(p, list(spec["paths"][p].keys()))
PY
# how the existing app loads the client (CDN/script tag) — open it to see the global
grep -niE "script src|LemmaClient|sdk" apps/ops-queue/html.html | head
```
Expected: the conversation REST paths (e.g. `POST /pods/{pod_id}/conversations`, `.../conversations/{id}/messages`, a stream/messages GET) and the `<script src=...>` the app uses for `window.LemmaClient`.

- [ ] **Step 2: Probe the live browser client for a conversation method**

Open the existing app in a browser (or read the served SDK bundle) and check whether `client.conversations` / `client.agents` exists with a send method. If `lemma` chrome/devtools aren't available, fetch the SDK script URL found in Step 1 and grep it:
```bash
# example: replace URL with the script src from Step 1
curl -s "<sdk script url>" | grep -oE "conversations|agents|sendMessage|createConversation" | sort -u | head
```
Expected: confirmation of a `conversations`/`agents` client namespace, or its absence.

- [ ] **Step 3: Record the confirmed transport**

Write the confirmed approach into the commit message, ONE of:
- **A (preferred):** `client.conversations.send({ agent_name: "concierge", message, conversation_id })` (or the exact method names found).
- **B (REST fallback):** authenticated `fetch` to `POST /pods/{pod_id}/conversations` (create) then `POST .../conversations/{id}/messages` (send) then poll/stream `GET .../conversations/{id}/messages`. The pod id is available to the app via the client/init payload.

```bash
git commit -q --allow-empty -m "docs: confirm browser conversation transport for customer-chat (Task 1)

Confirmed: <A or B, with exact method/endpoint names>"
```

---

## Task 2: `file_ticket` function

**Files:**
- Create: `functions/file_ticket/code.py`
- Create: `functions/file_ticket/file_ticket.json`
- Test: `tests/test_file_ticket.py`

- [ ] **Step 1: Write the failing test (pure helper)**

Create `tests/test_file_ticket.py`:
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests._load import load_fn

mod = load_fn("file_ticket")
p = mod.build_ticket_payload("Aanya Verma", "Cancel booking #16 and refund", "bk-123", "app_chat")
assert p["customer_name"] == "Aanya Verma"
assert p["raw_message"] == "Cancel booking #16 and refund"
assert p["channel"] == "app_chat"
assert p["status"] == "new"
assert p["booking_id"] == "bk-123"
# booking_id omitted when empty (so a no-booking ticket still validates)
p2 = mod.build_ticket_payload("Guest", "where is my pro", "", "app_chat")
assert "booking_id" not in p2
# default channel
assert mod.build_ticket_payload("Guest", "hi")["channel"] == "app_chat"
print("test_file_ticket OK")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tests/test_file_ticket.py`
Expected: FAIL — `FileNotFoundError` (no `code.py`).

- [ ] **Step 3: Implement the function**

Create `functions/file_ticket/code.py`:
```python
#input_type_name: FileTicketInput
#output_type_name: FileTicketResult
#function_name: file_ticket

from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


class FileTicketInput(BaseModel):
    customer_name: str
    message: str
    booking_id: str = ""
    channel: str = "app_chat"   # one of: whatsapp | app_chat | email


class FileTicketResult(BaseModel):
    ticket_id: str
    detail: str


def build_ticket_payload(customer_name: str, message: str, booking_id: str = "", channel: str = "app_chat") -> dict:
    payload = {
        "customer_name": customer_name,
        "raw_message": message,
        "channel": channel or "app_chat",
        "status": "new",
    }
    if booking_id:
        payload["booking_id"] = booking_id
    return payload


async def file_ticket(ctx: FunctionContext, data: FileTicketInput) -> FileTicketResult:
    pod = Pod.from_env()
    payload = build_ticket_payload(data.customer_name, data.message, data.booking_id, data.channel)
    created = pod.records.create("tickets", payload)   # INSERT fires new-ticket -> handle_ticket
    return FileTicketResult(ticket_id=created["id"], detail=f"Filed ticket for {data.customer_name}")
```

Create `functions/file_ticket/file_ticket.json`:
```jsonc
{
  "name": "file_ticket",
  "description": "Files a customer's (disambiguated) request as a new tickets row, which fires the handle_ticket engine to triage and resolve it within the existing gates. Used by the concierge agent to hand off — concierge never acts on bookings itself.",
  "type": "API",
  "code": { "$file": "code.py" },
  "permissions": { "grants": [
    { "resource_type": "datastore_table", "resource_name": "tickets", "permission_ids": ["datastore.table.read", "datastore.record.read", "datastore.record.write"] },
    { "resource_type": "datastore_table", "resource_name": "bookings", "permission_ids": ["datastore.table.read", "datastore.record.read"] }
  ] }
}
```

- [ ] **Step 4: Run the test + harness**

Run: `python3 tests/test_file_ticket.py` → `test_file_ticket OK`
Then: `python3 -c "from tests.jsonc import load; load('functions/file_ticket/file_ticket.json'); print('json ok')"` and `bash tests/run.sh` → ends `ALL TESTS PASSED`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -q -m "feat(file_ticket): concierge -> queue hand-off function"
```

---

## Task 3: `concierge` agent

**Files:**
- Create: `agents/concierge/concierge.json`
- Create: `agents/concierge/instruction.md`
- Test: `tests/test_concierge.py`

- [ ] **Step 1: Write the failing structural test**

Create `tests/test_concierge.py`:
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.jsonc import load

a = load("agents/concierge/concierge.json")
assert a["name"] == "concierge"
assert a["instruction"]["$file"] == "instruction.md"
# must be able to converse + ask clarifying questions
assert "POD" in a["toolsets"] and "USER_INTERACTION" in a["toolsets"]
# conversational agent: no fixed output_schema
assert "output_schema" not in a

grants = a["permissions"]["grants"]
tbl = {g["resource_name"]: g for g in grants if g["resource_type"] == "datastore_table"}
# read-only on data — NO write on bookings (answer-only; cannot move money)
for t in ["bookings", "tickets", "professionals", "provider_responses"]:
    assert t in tbl, f"missing read grant on {t}"
    assert "datastore.record.write" not in tbl[t]["permission_ids"], f"{t} must be read-only"
# can call the hand-off function + read the policy for RAG
assert any(g["resource_type"] == "function" and g["resource_name"] == "file_ticket"
           and "function.execute" in g["permission_ids"] for g in grants)
assert any(g["resource_type"] == "folder" and g["resource_name"] == "/knowledge" for g in grants)

instr = open("agents/concierge/instruction.md").read().lower()
for kw in ["file_ticket", "ask", "never", "booking"]:
    assert kw in instr, f"instruction missing: {kw}"
print("test_concierge OK")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tests/test_concierge.py`
Expected: FAIL — `FileNotFoundError` (no `concierge.json`).

- [ ] **Step 3: Create the agent bundle**

Create `agents/concierge/concierge.json`:
```jsonc
{
  "name": "concierge",
  "description": "Conversational customer-support front door. Answers questions from booking data + policy, asks clarifying questions, and files a clean ticket into the queue for the deterministic engine to resolve. Read-only on data; never moves money itself.",
  "instruction": { "$file": "instruction.md" },
  "toolsets": ["POD", "USER_INTERACTION"],
  "visibility": "POD",
  "permissions": { "grants": [
    { "resource_type": "datastore_table", "resource_name": "bookings", "permission_ids": ["datastore.table.read", "datastore.record.read"] },
    { "resource_type": "datastore_table", "resource_name": "tickets", "permission_ids": ["datastore.table.read", "datastore.record.read"] },
    { "resource_type": "datastore_table", "resource_name": "professionals", "permission_ids": ["datastore.table.read", "datastore.record.read"] },
    { "resource_type": "datastore_table", "resource_name": "provider_responses", "permission_ids": ["datastore.table.read", "datastore.record.read"] },
    { "resource_type": "folder", "resource_name": "/knowledge", "permission_ids": ["folder.read"] },
    { "resource_type": "function", "resource_name": "file_ticket", "permission_ids": ["function.execute"] }
  ] }
}
```

Create `agents/concierge/instruction.md`:
```markdown
# YesMadam Concierge — live customer chat

You are the YesMadam customer-support concierge, chatting **directly with a customer** in
real time (YesMadam = at-home salon & wellness: haircut, facial, massage, manicure,
waxing). Be warm, brief, and concrete.

## What you can and cannot do
- You can **read** bookings, tickets, professionals, provider coordination state, and the
  support policy (`/knowledge/support-policy.md`).
- You **cannot** change a booking or move money yourself. To get something done, you
  **file a ticket** with the `file_ticket` tool; the support desk engine takes the real
  action (refund / reschedule / replacement) within its rules and a human reviews the hard
  cases. Never tell the customer an action is done unless a ticket or booking confirms it.

## How to handle the conversation
1. **Find their booking.** Match on what they say (name, service, "my massage"). If you
   can't tell which booking they mean, **ask** (use the ask-the-user tool) — don't guess.
2. **Answer truthfully from data.** "Why is my pro late?" → read the booking's
   `provider_state`, `check_in_at`, `scheduled_at`, and any matching `provider_responses`
   row, and explain plainly (e.g., "Karan checked in at 4:25 and is on his way — about 10
   minutes out"). Never invent facts, times, or names.
3. **Ask clarifying questions** whenever there's a choice or ambiguity — refund vs
   replacement, which of two bookings, or to confirm before you file anything.
4. **Apply policy** when explaining eligibility: the free-reschedule window, no-show
   rights (replacement or refund), the refund cap, and that refunds only apply to prepaid
   bookings. If proof of service exists (check-in / OTP), be honest that a refund may need
   review.
5. **Hand off when intent is clear and confirmed.** Call `file_ticket` with: `customer_name`,
   a concise one-line `message` capturing exactly what they want (e.g. "Cancel booking #16
   and issue a full refund — customer confirmed"), and `booking_id` when you know it.
6. **Report the outcome back.** After filing, tell them it's being processed. When they
   reply again, **re-read the ticket** (by the customer's recent ticket) and the booking,
   and relay the real result: refunded (amount), rescheduled (new time), replacement
   assigned (who), or "flagged to a teammate" if it needs human review. If it's still
   processing, say so — don't claim a result you can't see.

## Tone
Apologise once and sincerely when something went wrong; don't over-apologise. One question
at a time. Short messages. No internal jargon (don't say "ticket #", "gate", or "workflow"
to the customer — say "I've logged this" / "our team").
```

- [ ] **Step 4: Run the test + harness**

Run: `python3 tests/test_concierge.py` → `test_concierge OK`
Then: `python3 -c "from tests.jsonc import load; load('agents/concierge/concierge.json'); print('json ok')"` and `bash tests/run.sh` → `ALL TESTS PASSED`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -q -m "feat(concierge): conversational customer agent (read-only + file_ticket hand-off)"
```

---

## Task 4: `customer-chat` pod App

**Files:**
- Create: `apps/customer-chat/customer-chat.json`
- Create: `apps/customer-chat/html.html`
- Test: `tests/test_customer_chat.py`

- [ ] **Step 1: Write the failing string/structure test**

Create `tests/test_customer_chat.py`:
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.jsonc import load

cfg = load("apps/customer-chat/customer-chat.json")
assert cfg["name"] == "customer-chat"
assert cfg.get("public_slug"), "needs a public_slug for the URL"

html = open("apps/customer-chat/html.html").read()
assert "LemmaClient" in html, "must use the browser LemmaClient"
assert "concierge" in html, "must target the concierge agent"
assert "sendMessage" in html, "must have a send-message handler"
print("test_customer_chat OK")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tests/test_customer_chat.py`
Expected: FAIL — `FileNotFoundError` (no `customer-chat.json`).

- [ ] **Step 3: Create the app config**

Create `apps/customer-chat/customer-chat.json`:
```jsonc
{
  "name": "customer-chat",
  "description": "Customer-facing chat: a live conversation with the YesMadam concierge agent. The customer asks questions ('why is my pro late?', 'can I get a refund?'); concierge answers from booking data, asks clarifying questions, files a ticket into the desk engine, and reports the outcome back.",
  "public_slug": "yesmadam-chat"
}
```

- [ ] **Step 4: Create the chat UI**

Create `apps/customer-chat/html.html`. Transport is **confirmed (Task 1)**: load the **first-party** SDK exactly like `ops-queue` (`base + "/public/sdk/lemma-client.js"`, base = `(window.__LEMMA_CONFIG__.apiUrl || location.origin)` — same-origin, no CDN/SRI concern), then drive a **multi-turn** conversation with `client.conversations()`: `createForAgent("concierge", {title})` ONCE, then `messages.send` per turn (do NOT use `client.agents.run` — it creates a fresh conversation each call, breaking context). Prefer streaming via `sendMessageStream`; fall back to `messages.send` + poll `messages.list`.
```html
<!doctype html>
<html lang="en"><head>
<meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>YesMadam · Chat</title>
<!-- SDK is loaded first-party at runtime by the IIFE in <script> below — no CDN, no SRI. -->
<style>
  :root{--brand:#e6007e;--brand-deep:#b80064;--blush:#fff6fa;--plum:#2a0e22;--line:#f4dce8;--ink-2:#6e5560}
  *{box-sizing:border-box} body{margin:0;font-family:"Hanken Grotesk",system-ui,sans-serif;background:var(--blush);color:var(--plum);height:100vh;display:flex;flex-direction:column}
  header{padding:16px 20px;background:linear-gradient(185deg,#3a0f2c,#2a0e22);color:#fff;font-weight:700}
  header small{display:block;font-weight:500;font-size:12px;color:#ff9ad0}
  #thread{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:10px}
  .msg{max-width:78%;padding:10px 14px;border-radius:14px;font-size:14px;line-height:1.45;box-shadow:0 1px 2px rgba(42,14,34,.06);white-space:pre-wrap}
  .me{align-self:flex-end;background:var(--brand);color:#fff;border-bottom-right-radius:4px}
  .bot{align-self:flex-start;background:#fff;border:1px solid var(--line);border-bottom-left-radius:4px}
  .typing{color:var(--ink-2);font-style:italic;font-size:13px;align-self:flex-start}
  form{display:flex;gap:8px;padding:14px 16px;border-top:1px solid var(--line);background:#fff}
  input{flex:1;padding:12px 14px;border:1px solid var(--line);border-radius:12px;font-size:14px}
  button{padding:12px 18px;border:none;border-radius:12px;background:var(--brand);color:#fff;font-weight:700;cursor:pointer}
</style></head>
<body>
  <header>YesMadam Support<small>Chat with our assistant</small></header>
  <div id="thread"></div>
  <form id="f"><input id="i" placeholder="Ask about your booking…" autocomplete="off" />
    <button type="submit">Send</button></form>
<script>
  // First-party SDK loader (identical pattern to the ops-queue app).
  (function(){
    var cfg=window.__LEMMA_CONFIG__||{};
    var base=(cfg.apiUrl||window.location.origin).replace(/\/$/,"");
    var s=document.createElement("script");
    s.src=base+"/public/sdk/lemma-client.js";
    s.onload=boot;
    s.onerror=function(){add("Couldn't load the assistant. Please refresh.","bot");};
    document.head.appendChild(s);
  })();

  const thread=document.getElementById("thread");
  function add(text,cls){var d=document.createElement("div");d.className="msg "+cls;d.textContent=text;thread.appendChild(d);thread.scrollTop=thread.scrollHeight;return d;}
  let client=null, convNs=null, conv=null;

  async function boot(){
    client=new window.LemmaClient.LemmaClient();
    const state=await client.initialize();
    if(state.status!=="authenticated"){client.auth.redirectToAuth();return;}
    convNs=client.conversations();                                   // namespace is a function call
    conv=await convNs.createForAgent("concierge",{title:"Customer chat"});  // ONE conversation, reused
    add("Hi! I'm the YesMadam assistant. Ask me anything about your booking — running late, reschedule, or a refund.","bot");
  }

  async function sendMessage(text){
    // Preferred: stream the reply as it generates.
    if(typeof convNs.sendMessageStream==="function"){
      const bubble=add("…","bot"); let acc="";
      const stream=await convNs.sendMessageStream(conv.id,{content:text});
      for await (const ev of stream){
        const chunk=(ev&&(ev.delta||ev.content||ev.text||ev.message))||"";
        if(chunk){acc+=chunk;bubble.textContent=acc;thread.scrollTop=thread.scrollHeight;}
      }
      if(!acc) bubble.textContent="(working on it — ask again in a moment)";
      return;
    }
    // Fallback: send, then poll the message list for the new assistant message.
    await convNs.messages.send(conv.id,{content:text});
    const t=add("…","typing");
    for(let i=0;i<30;i++){
      await new Promise(r=>setTimeout(r,1000));
      const res=await convNs.messages.list(conv.id);
      const items=(res&&(res.items||res))||[];
      const last=items.filter(function(m){return m.role==="assistant";}).pop();
      if(last&&last.content){t.remove();add(last.content,"bot");return;}
    }
    t.remove();add("Still working on it — give me a moment and ask again.","bot");
  }

  document.getElementById("f").addEventListener("submit",async function(e){
    e.preventDefault();const i=document.getElementById("i");const text=i.value.trim();if(!text)return;
    i.value="";add(text,"me");
    try{await sendMessage(text);}catch(err){add("Sorry — something went wrong reaching the assistant. Please try again.","bot");}
  });
</script>
</body></html>
```
**Note for the implementer:** the SDK loader + `client.conversations()`/`createForAgent`/`messages.send`/`sendMessageStream` names are confirmed against the served SDK (`api.lemma.work/public/sdk/lemma-client.js`). The stream event field (`delta`/`content`/…) and `messages.list` return shape are best-effort — confirm them by inspecting the live `client` in the running app during Task 5 (chrome-devtools / console) and adjust if needed. Run `node --check` on the extracted `<script>` body before committing.

- [ ] **Step 5: Run the test + JS check + harness**

Run:
```bash
python3 tests/test_customer_chat.py
python3 - <<'PY'
import re
html=open("apps/customer-chat/html.html").read()
body=max(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S), key=len)
open("/tmp/cc.js","w").write(body)
PY
node --check /tmp/cc.js && echo "app JS OK"
bash tests/run.sh
```
Expected: `test_customer_chat OK`, `app JS OK`, `ALL TESTS PASSED`.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -q -m "feat(customer-chat): themed customer chat app wired to the concierge agent"
```

---

## Task 5: Live import + end-to-end verification

**Files:** none (verification). Fix-and-re-import any resource whose live shape differs.

- [ ] **Step 1: Ensure session + runtime**

Run: `lemma pods list` (valid session? if `INVALID_REFRESH_TOKEN`, ask the user to `!lemma auth login`). Then start the agent runtime: `lemma daemon start` (as a tracked background process) and confirm `lemma daemon status` / the daemon log shows `ready ack`.

- [ ] **Step 2: Import the new resources**

Run:
```bash
lemma pods import functions/file_ticket 2>&1 | tail -4
lemma pods import agents/concierge 2>&1 | tail -4
lemma pods import apps/customer-chat 2>&1 | tail -4
```
Expected: `file_ticket`, `concierge`, `customer-chat` created. On `MISSING_WORKLOAD_RESOURCE_GRANT`, add the missing grant and re-import.

- [ ] **Step 3: Verify the conversation (CLI first — fastest)**

With a seeded en-route / scheduled booking present (e.g. a no-show booking with `provider_state` set, or seed one), run:
```bash
lemma chat concierge -m "Hi, I booked a massage under <CustomerName> — why is my therapist late?"
```
Expected: a truthful answer from the booking's `provider_state`/`check_in_at`. Then continue the conversation (`lemma conversations send` or interactive `lemma chat concierge`) with "Can I get a refund?" → expect a **clarifying question** (refund vs replacement / confirm). Confirm → concierge calls `file_ticket`.

- [ ] **Step 4: Verify the hand-off + loop-back**

After concierge files the ticket: confirm a new `tickets` row exists (`lemma records list tickets --limit 3`) and that `handle_ticket` resolved it (booking changed / ticket `auto_resolved` or parked `waiting_approval` per the gates). Continue the chat ("did my refund go through?") → concierge should read the ticket/booking back and relay the **real** outcome (refunded amount / replacement / "flagged to a teammate"), not a fabricated one.

- [ ] **Step 5: Verify the chat App**

Open `https://yesmadam-chat.apps.lemma.work` (authenticate), run the same flow in the UI: a question → an answer → a clarifying question → confirm → the outcome appears in-thread. Capture a screenshot for the demo.

- [ ] **Step 6: Clean up test artifacts + commit**

Delete any test bookings/tickets/conversations created during verification (keep the original seed). Then:
```bash
git commit -q --allow-empty -m "test: live e2e of concierge conversation + hand-off + loop-back"
```
Update `~/.claude/.../memory/yesmadam-support-desk-live.md` with the concierge agent, `file_ticket`, and the `customer-chat` app (slug `yesmadam-chat`).

---

## Self-review notes (for the implementer)

- **Spec coverage:** concierge agent (Task 3), `file_ticket` hand-off (Task 2), `customer-chat` app (Task 4), transport unknown isolated + fallback (Task 1), live e2e incl. read-back (Task 5). Answer-only / read-only-on-bookings is enforced by the Task 3 test. Reuse of `handle_ticket` gates is inherent (file_ticket just inserts a ticket — the unchanged engine + gates resolve it).
- **The one platform unknown** (browser conversation API) is isolated to Task 1 with a written REST fallback; it doesn't block Tasks 2–3.
- **Names are consistent:** `file_ticket` (fn) / `build_ticket_payload` (helper) / `concierge` (agent) / `customer-chat` (app, slug `yesmadam-chat`) used identically across tasks.
- **Additive guarantee:** no task modifies `handle_ticket`, existing tables, or existing functions — verify `git diff --stat` per task touches only the new paths.
