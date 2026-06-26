# Concierge — Conversational Customer Front Door — Design

**Date:** 2026-06-26
**Pod:** YesMadam Support Desk (`/home/sahl/Documents/lemma/support-desk/`)
**Status:** Approved design → ready for implementation plan

## Problem / goal

Today the pod is an **ops-side queue runner**: a ticket row appears and the `handle_ticket`
engine triages and resolves it. There is no way for a *customer* to interact — to ask
*"why is my pro late?"*, then *"can I get a refund?"*, get context-aware answers and
relevant follow-up questions, and have it resolved end-to-end in a conversation.

Build a **conversational customer front door** — a multi-turn agent ("concierge") with a
chat UI — that understands a series of messages, answers truthfully from booking data,
asks clarifying questions when needed, and **hands off to the existing deterministic
engine** to take the real action (refund / reschedule / replacement), then reports the
engine's actual outcome back in the conversation. No hardcoding: the agent reasons over
the live thread and pod data.

## Scope decisions (locked with user)

- **Action model: answer-only, hand off.** Concierge **never moves money or mutates a
  booking.** It answers, asks clarifying questions, and — once intent is clear and
  confirmed — files a clean ticket into the existing queue. The proven `handle_ticket`
  engine takes the action within its existing gates. Concierge then reads the resolution
  back to the customer.
- **Interface: a customer chat box in the UI** — a new pod App `customer-chat`
  (single-file HTML, same pattern as `ops-queue`), themed to match.
- **Reuse the safety rails.** All money/booking decisions stay in the existing engine
  (refund ≤ ₹1,500 cap, anti-fraud `verify_service`, en-route lock, escalation). The
  conversational layer adds **zero** new ability to act. Positioning: *"a conversational
  front door that routes into a deterministic engine,"* not "a chatbot that decides
  refunds."
- **Additive only.** Nothing existing changes; `handle_ticket` and all current resources
  are untouched.

## Platform facts (verified)

- Lemma agents are conversational and multi-turn: `lemma chat <agent>` /
  `lemma conversations send`; conversation memory is managed by the platform.
- Agents support `ask_user` (clarifying questions surface as approval/question prompts)
  and gated tool calls (`conversations approvals`).
- Agents take resource grants (read tables, read files for RAG) and can call functions as
  tools (grant `function`/`function.execute`).
- A pod **App** (single-file HTML) runs an authenticated `window.LemmaClient.LemmaClient()`
  (as `ops-queue` does: `client.auth`, `client.records`, `client.datastore`,
  `client.workflows`). Conversations are REST under `/pods/{pod_id}/conversations`.
- `surfaces` is for Slack/Teams/etc. only — **not** a generic web chat — so the chat lives
  in a pod App.
- **Runtime:** the conversational agent runs on the same agent runtime as `triage` — the
  free Claude Code **daemon** must be running (`lemma daemon start`) for live replies.

## Components

### 1. Agent `concierge` (new) — `agents/concierge/{concierge.json, instruction.md}`
- **Toolset:** POD (read), plus the `file_ticket` function as a tool.
- **Grants (read-only on data):** `bookings`, `tickets`, `professionals`,
  `provider_responses` (`datastore.table.read` + `datastore.record.read`); folder
  `/knowledge` (`folder.read`) for policy RAG; `function.execute` on `file_ticket`.
  **No write grant on `bookings`** — concierge cannot act on money.
- **Instruction (`instruction.md`)** — behaviour:
  1. You are a YesMadam customer-support concierge in a live chat with a customer.
  2. **Identify the customer's booking** from what they say (name / service / "my
     massage"); if you can't tell which booking, **ask** (`ask_user`).
  3. **Answer truthfully from data**, never invent. "Why is he late?" → read the booking's
     `provider_state`, `check_in_at`, `scheduled_at`, and any `provider_responses` row, and
     explain (e.g., "Karan checked in at 4:25 and is en route, ~10 min away").
  4. **Ask a clarifying question** whenever the resolution is ambiguous or has options —
     e.g., refund vs replacement, which of two bookings, confirm before filing.
  5. Retrieve and apply the **policy** (`/knowledge/support-policy.md`) when explaining
     eligibility (refund window, no-show rights, the ₹1,500 cap, prepaid logic).
  6. Once intent is **clear and the customer confirms**, call **`file_ticket`** with a
     concise, disambiguated `message`, the `booking_id`, and the customer's `name`.
  7. After filing, tell the customer it's being processed; when they next message (or you
     re-check), **read the ticket's `status` + `draft_reply`** and relay the **actual
     outcome** — never claim a refund that didn't happen.
  8. Never promise or state an action as done unless the ticket/booking confirms it. You
     do not move money; the desk engine does, within its rules.

### 2. Function `file_ticket` (new) — `functions/file_ticket/{code.py, file_ticket.json}`
- **Input:** `customer_name: str`, `message: str`, `booking_id: str = ""`,
  `channel: str = "app_chat"`.
- **Behaviour:** create a `tickets` row (`customer_name`, `raw_message=message`,
  `booking_id` if given, `channel`, `status="new"`). The existing `new-ticket` schedule
  fires `handle_ticket` on the INSERT → the engine triages + acts within its gates. Return
  the new `ticket_id` so concierge can read the resolution back.
- **Grants:** `tickets` (`datastore.table.read`, `datastore.record.read`,
  `datastore.record.write`); `bookings` (read, to validate the booking_id exists).
- **Pure helper (testable):** `build_ticket_payload(customer_name, message, booking_id,
  channel) -> dict` — assembles the row; unit-tested without a Pod.
- Uses `pod.records.create("tickets", payload)["id"]` (verified: returns the row with id).

### 3. App `customer-chat` (new) — `apps/customer-chat/{customer-chat.json, html.html}`
- Single-file HTML, themed to match the YesMadam look (blush canvas, magenta, the seal).
- On load: `new window.LemmaClient.LemmaClient()` → `initialize()` →
  `auth.redirectToAuth()` if unauthenticated (demo viewer authenticates).
- Starts/continues a conversation with the `concierge` agent and renders the thread
  (customer right, concierge left), an input box, and a streaming reply.
- Renders concierge's **clarifying questions inline** as the question bubble the customer
  answers (the `ask_user` prompt).
- When the filed ticket resolves, the engine's outcome surfaces in-thread (concierge's
  read-back).
- **Conversation transport (confirm in plan, fallback known):** prefer the browser
  `LemmaClient` conversation method (e.g. `client.conversations.send(agent, message)` /
  `client.agents.run`); if the browser client doesn't expose it, POST to
  `/pods/{pod_id}/conversations` (+ messages/stream) using the authenticated client's
  fetch/token. **Task 1 of the plan verifies the exact browser API; the REST fallback is
  the backstop.**

## Data flow

```
Customer (chat UI) ──▶ concierge conversation (multi-turn, context, ask_user)
   │  answers "why late?" from bookings/provider_responses + policy RAG
   │  asks clarifying Qs; on confirm:
   └─▶ file_ticket(message, booking_id) ──INSERT──▶ tickets row
            └─ new-ticket schedule ─▶ handle_ticket (UNCHANGED engine):
                 triage → verify_service → gate (cap / anti-fraud / en-route) →
                   execute_resolution (refund/reschedule/replace)  OR  human form
   ◀── concierge reads ticket.status + draft_reply ──▶ relays the real outcome to the customer
```

## Error handling / edge cases

- **Ambiguous request / which booking** → `ask_user`, don't guess.
- **No matching booking** → concierge says a human will follow up and files a ticket
  (engine escalates: no `booking_found` → human form). Never fabricates a resolution.
- **Off-policy / sales question** → answer what it can from policy; if it needs action,
  file it (engine routes `other` → escalate).
- **Engine still processing on read-back** → "still going through — one moment," re-check
  next turn (don't claim done).
- **Over-cap refund / service-proven / en-route booking** → the engine blocks/escalates;
  concierge relays "flagged to a teammate," not "refunded." (Reuses the proven gates.)
- **Runtime/daemon down** → the filed ticket sits `new` until the runtime is up; concierge
  should set expectations ("logged; you'll get an update shortly") rather than hang.
- **Agent must not state an action as done without confirming it in the ticket/booking** —
  explicit instruction guard against hallucinated refunds.

## Testing

- **Pure unit (local, no cloud):** `build_ticket_payload` shapes the row correctly
  (fields, channel default, booking_id optional) — `tests/test_file_ticket.py`.
- **Structural:** `file_ticket.json`, `concierge.json`, `customer-chat.json` parse;
  `code.py` compiles; grants present (`tickets` write, `function.execute` on file_ticket).
- **App static:** `html.html` references the concierge agent + a conversation call + renders
  a thread (string checks); the `<script>` body passes `node --check`.
- **Live e2e (daemon up):** open `lemma chat concierge` (CLI) — ask "why is my pro late?"
  for an en-route booking (expect a truthful ETA answer), then "can I get a refund?"
  (expect a clarifying question), confirm → `file_ticket` fires → `handle_ticket` resolves
  → concierge relays the outcome. Then the same flow in the `customer-chat` app.

## Non-goals

- Concierge taking any booking/money action itself (it only files tickets).
- A public/anonymous customer chat with a server-side token proxy (the demo App is
  authenticated; a public deployment is a later step).
- Changing `handle_ticket` or any existing resource.
- Voice / WhatsApp / SMS channels (the same agent could back a Slack/Teams `surface`
  later, but that's out of scope).

## Components touched (summary)

| Kind | Item | Change |
|---|---|---|
| Agent | `concierge` | **new** (conversational, read-only + file_ticket) |
| Function | `file_ticket` | **new** |
| App | `customer-chat` | **new** (authenticated chat UI) |
| Everything else (`handle_ticket`, tables, other functions/workflows/schedules) | — | **unchanged** |
