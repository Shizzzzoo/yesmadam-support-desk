# Support Desk — Lemma pod bundle

An at-home services marketplace (YesMadam-style: salon & wellness at home) support
desk. An **agent runs the inbound ticket queue**: it classifies each ticket, retrieves
the policy, finds the customer's booking, and **takes the real booking action**
(reschedule / refund / replacement) on its own — or **escalates the hard cases to a
human** for approval. It does the work of operating support; it is not a chatbot.

> Full product rationale, judging alignment, and design decisions live in
> `../PROJECT.md`. This README is the operator/build runbook.

## What's in the bundle

| Layer | Resource | Role |
|---|---|---|
| Tables | `bookings` | the system the agent **acts on** — this row visibly changes |
| | `tickets` | the queue; a new row fires the workflow |
| | `ticket_events` | audit trail (proves "it did the work") |
| | `professionals` | availability for no-show replacements |
| Files | `/knowledge/support-policy.md` | RAG source: refund/reschedule/no-show rules + gate thresholds |
| Functions | `apply_triage` | persists the agent's classification onto the ticket |
| | `execute_resolution` | the reliable verb: mutates booking + resolves ticket + logs events |
| Agent | `triage` | read-only judgment → rich `output_schema` the gate routes on |
| Workflow | `handle_ticket` | triage → structural gate → auto action OR human approval form |
| Schedule | `new-ticket` | `tickets` INSERT → `handle_ticket` |
| App | `ops-queue` | the operator screen (queue · decision · linked booking · approvals · metrics) |

## The core loop

```
new ticket (INSERT) ──schedule──▶ handle_ticket:
  AGENT triage      → classify, find booking, draft reply, propose action (read-only)
  FUNCTION apply_triage → write classification onto the ticket
  DECISION gate     → action≠none AND confidence≥0.8 AND category∈4-types
                       AND booking_found AND refund_amount≤₹1500 ?
     ── yes ─▶ FUNCTION execute_resolution (actor=agent) → booking row changes, ticket=auto_resolved
     ── no  ─▶ FORM (human approval) → DECISION approved?
                  ── yes ─▶ execute_resolution (actor=human) → ticket=resolved
                  ── no  ─▶ execute_resolution (action=none)  → ticket=escalated
```

The **structural gate** — not the model's self-reported confidence — decides what the
agent may do alone. Refunds over ₹1,500, ambiguous/compound tickets, missing bookings,
and low confidence are escalated **by design**.

## Setup (non-bundled state — do this after import)

Records and file bytes do **not** travel in bundles. Steps:

```bash
# 0. Stack + auth (see ../PROJECT.md §5 for local install). Need Docker/Podman + a model key.
lemma servers select local && lemma auth login

# 1. Create the pod shell (import never creates it), then import the bundle.
lemma pods create support-desk --org <your-org> --description "At-home services support desk"
lemma pods import ./support-desk --dry-run     # validate everything first
lemma pods import ./support-desk               # upsert all layers in dependency order
lemma pods doctor support-desk                 # check grants/targets/schedule wiring

# 2. Seed bookings, professionals, policy file, and tickets (this makes it demo itself).
bash ./support-desk/seed/seed.sh
```

## Day-1 spike (smallest test that proves the differentiator)

Before trusting the whole graph, confirm a function can mutate a booking:

```bash
B=$(lemma --output json records list bookings --limit 1 | python3 -c "import sys,json;print(json.load(sys.stdin)['items'][0]['id'])")
T=$(lemma --output json records list tickets  --limit 1 | python3 -c "import sys,json;print(json.load(sys.stdin)['items'][0]['id'])")
lemma functions run execute_resolution --data "{\"ticket_id\":\"$T\",\"action\":\"reschedule\",\"booking_id\":\"$B\",\"proposed_new_time\":\"2026-06-28T18:00:00+05:30\",\"reply\":\"moved\",\"resolution_status\":\"auto_resolved\",\"actor\":\"agent\"}"
lemma records get bookings $B    # status=rescheduled, last_action set → the work happened
```

## Verify each layer (build order)

```bash
lemma tables get bookings tickets ticket_events professionals
lemma functions run apply_triage --file ./support-desk/payloads/apply_triage.json   # fill ids first
lemma agents run triage "{\"ticket_id\":\"$T\"}"        # check output_schema conforms
lemma workflows validate ./support-desk/workflows/handle_ticket
lemma workflows runs list handle_ticket                # seeded tickets should have runs
lemma schedules get new-ticket                         # active? DATASTORE on tickets INSERT?
lemma apps deploy ops-queue ./support-desk/apps/ops-queue/html.html
lemma apps open ops-queue
```

## End-to-end smoke test

```bash
# create one ticket → the desk should auto-resolve it and change the booking
lemma records create tickets --data '{"customer_name":"Aarav Mehta","channel":"whatsapp","raw_message":"Move my haircut on the 28th to 6 PM."}'
lemma workflows runs list handle_ticket          # newest run → COMPLETED
lemma query run "select status, count(*) from tickets group by status"
lemma query run "select code, status, last_action from bookings where status!='scheduled'"
```

Expected after seeding: most tickets `auto_resolved` with their booking row changed
(`rescheduled` / `cancelled` / replacement assigned); the over-cap refunds, the
compound ticket, the off-policy question, and the no-booking ticket sitting in the
**approval inbox** for a human.

## Things to re-check on Day 1 (the SDK is fresh)

- Exact JMESPath gate condition compiles (`lemma workflows validate`) — `&&` / backtick literals.
- DATASTORE trigger really exposes the new id at `start.metadata.record_id`.
- The HTML app's `workflows.runs.waitingAssignedToMe()` returns the **unassigned** FORM
  waits; if not, give `escalate_form` an `assignee_pod_member_id` (an ops member) and re-import.
- The `agent_decision` JSON round-trips so the app can render reasoning.
