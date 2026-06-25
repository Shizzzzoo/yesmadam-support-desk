# Provider Coordination Loop — Design

**Date:** 2026-06-25
**Pod:** YesMadam Support Desk (`/home/sahl/Documents/lemma/support-desk/`)
**Status:** Approved design → ready for implementation plan

## Problem

Today the support desk resolves a "customer-waiting" ticket (no-show / "where's my
pro") one-sidedly: the agent classifies it and immediately acts on the booking
(replacement, refund, informational reply). The professional is never consulted, and two
halves of the system can act on stale state — most dangerously, **a refund-and-cancel can
fire while the assigned professional is already on their way.** The cancel can also come
from a *different* ticket (e.g. the customer separately emails "just cancel and refund").

## Goal

When a customer-waiting ticket arrives, **proactively alert the assigned professional**
("a client is waiting"), give them a small menu of responses, and let their choice (or
their silence) drive the resolution — while **guaranteeing** that no refund-and-cancel
fires out from under a committed professional, and that the customer is *never* left
waiting indefinitely.

## Scope decisions (locked with user)

- **Channel: modeled in the pod.** Outbound alert rides the existing notify seam
  (Gmail connector, degrades gracefully). The professional's reply is captured as a
  structured row in a new `provider_responses` table — the same shape a future inbound
  SMS/WhatsApp webhook would write. No second app, no provider auth.
- **Race policy: sequence + en-route lock.** Customer-waiting tickets alert the pro and
  wait for a reply before any cancel/refund. Independently, an `en_route` lock on the
  booking blocks refunds from *any* ticket while the pro is committed (reuses the
  existing proof-of-service gate pattern).
- **Provider menu: four options** — running late (ETA N min), reschedule to a new time,
  can't make it today, already on-site (false-complaint).
- **SLA: 5 minutes.** If the pro does not choose within 5 minutes, their option set
  **expires**, the customer is resolved automatically (see `stand_down`), and a late
  reply is a no-op (the pro is told to stand down).
- **Customer is told up front** the pro was messaged from YesMadam's side and to hold
  ~5 minutes, with an explicit promise of automatic resolution if no reply.

## Data model

### New table `provider_responses` (shared, `enable_rls: false`)
One row per coordination event.

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `ticket_id` | UUID FK → `tickets.id` | originating customer-waiting ticket |
| `booking_id` | UUID FK → `bookings.id` | |
| `professional_name` | TEXT | who was alerted |
| `status` | ENUM | `awaiting`, `late`, `reschedule`, `on_site`, `cant_make_it`, `no_response`, `customer_accepted`, `customer_declined` — default `awaiting` |
| `eta_minutes` | INT | for `late` |
| `proposed_new_time` | DATETIME | for `reschedule` |
| `alerted_at` | DATETIME | default now — the SLA clock |
| `responded_at` | DATETIME | when the pro/customer last acted |
| `note` | TEXT (max 1900) | free text / audit |

The 5-minute SLA is a **code constant** (`SLA_MINUTES = 5`), not a column.

### `bookings` — add `provider_state`
ENUM `idle`, `alerted`, `en_route`, `stood_down`; default `idle`. This column is the
**refund lock**.

- `idle` — normal
- `alerted` — pro pinged, awaiting reply (soft hold)
- `en_route` — pro committed to come (late / on-site / accepted reschedule); **refunds blocked**
- `stood_down` — pro out or timed out; replacement & refund now allowed

### `professionals` — add `contact_email`
TEXT (max 200). The alert recipient; reuses the Gmail seam. (A `phone` column can be
added later for the SMS swap — out of scope now.)

### `tickets.status` — add `awaiting_provider`
New enum value, distinct from `waiting_approval` (which is the ops human). A ticket
parked while we wait on the professional.

### State machine
```
idle ──(no_show / where_is_pro ticket)──▶ alerted
  alerted ── late / on_site ───────────────▶ en_route     (lock on; customer told ETA)
  alerted ── reschedule ──▶ offer to customer ── accepted ─▶ en_route (rescheduled)
                                              └─ declined ─▶ stood_down ──▶ resolve
  alerted ── cant_make_it / no_response (SLA) ─────────────▶ stood_down ──▶ resolve
```

## Flows

### A. `handle_ticket` — new alert branch
- `verify_service` is extended to also return `provider_state` (it already loads the
  booking), so the gate can read it without a new function.
- New **gate rule, evaluated before the auto-resolve rule:**
  > `triage.category ∈ {no_show, where_is_pro} AND triage.booking_found AND verify_service.provider_state != 'stood_down'` → node `alert_provider`
- **`alert_provider` (new function):**
  - Load booking + professional (by name) → `contact_email`.
  - **Idempotency:** if `provider_state ∈ {alerted, en_route}` (another waiting ticket
    for the same booking), do **not** re-alert; link this ticket to the open response
    row, set the holding reply, end.
  - Otherwise: create the `provider_responses` row (`awaiting`, `alerted_at = now`); set
    `booking.provider_state = 'alerted'`; call `notify_provider` (emails the pro the four
    options); set `ticket.status = 'awaiting_provider'` and `draft_reply` to the customer
    holding message; log a `ticket_events` row.
  - → `notify` (email the customer the holding note) → `end`.
- Customer holding message:
  > "We've messaged your professional from YesMadam's side — please hold ~5 minutes while
  > they confirm. If we don't hear back, we'll refund you automatically."

### B. New workflow `provider_reply`
**Start:** `DATASTORE_EVENT` on `provider_responses` UPDATE.

- **Guard node (first):** if the booking is already `cancelled`/`completed`, or
  `provider_state == 'stood_down'` (already resolved), → `stand_down_notice` (email the
  pro "too late, already resolved") → `end`. *Handles late replies after expiry.*
- **Route (DECISION) on `provider_responses.status`:**
  - `late` → `commit_en_route`: `provider_state = en_route`,
    `last_action = "Pro en route, ETA {eta}m"`, customer reply = "Good news — {pro} is on
    the way (~{eta} min)", ticket resolved.
  - `on_site` → `commit_en_route` **plus** route the ticket to human
    (`waiting_approval`) with the proof-of-service summary (likely false complaint);
    refund stays locked.
  - `reschedule` → `offer_reschedule`: email the customer the proposed time and ask them
    to confirm/decline; hold `provider_state = en_route`; ticket stays `awaiting_provider`.
  - `customer_accepted` → `apply_reschedule`: `execute_resolution(action=reschedule,
    proposed_new_time=…)` → resolved.
  - `customer_declined` → `stand_down`.
  - `cant_make_it` → `stand_down`.
  - `no_response` → `stand_down`.
- **`stand_down` (new function):** sets `provider_state = 'stood_down'`, then calls the
  **existing** `execute_resolution(action='assign_replacement', …)`, which already falls
  back to a full refund when no active same-service pro exists in the area. Resolves the
  ticket and emails the customer the outcome. *(One proven path; replacement-when-
  possible, refund otherwise — see Judgment calls.)*

**Anti-fragility invariant:** `provider_reply` **never writes to `provider_responses`.**
It reads the row and mutates only `bookings` / `tickets` / `ticket_events`. All
`provider_responses.status` transitions come from external actors (the pro's reply, the
customer's reply, the SLA sweeper). This makes UPDATE-event feedback loops impossible.

### C. SLA sweeper `provider-sla` (time-based schedule)
A cron schedule (~every minute) runs **`sweep_provider_sla` (new function):**
- Any `awaiting` row with `alerted_at` older than `SLA_MINUTES` → set `status =
  'no_response'` (which fires `provider_reply` → `stand_down`).
- A `reschedule` offer with no customer reply past the same window → set `status =
  'customer_declined'`.

**Platform dependency (verify first):** Lemma must support a time-based (cron) schedule;
the existing schedule is event-based. **First task in the implementation plan is to
confirm this.** If cron is unsupported, the fallback is lazy expiry — `alert_provider`
and `provider_reply`, and the ops app on load, each sweep overdue `awaiting` rows — so
the timeout guarantee never depends on a feature that may not exist.

## Race guard (the refund lock)

Extend the existing refund-blocking rule in the `handle_ticket` gate (do not invent a new
mechanism):
> `triage.proposed_action == 'refund' AND (verify_service.service_proven == true OR verify_service.provider_state ∈ {alerted, en_route})` → `escalate_form`

A separate "cancel and refund" ticket arriving while the pro is committed therefore parks
for a human (who sees the provider state + ETA in the form) instead of silently
cancelling. Once `stood_down`, refunds flow normally again.

## Notifications

- **`notify_provider` (new function):** mirrors `notify_customer` — emails the assigned
  pro the alert + the four options via the Gmail seam. Degrades gracefully: no
  `contact_email` → log a `ticket_events` row and proceed (the SLA sweeper still resolves
  the customer). Never breaks the run.
- Customer-facing messages reuse `notify_customer` (drafts already set on the ticket).

## Surfacing (in-pod `ops-queue` app) + demo seed

- App: an `awaiting_provider` ticket shows "Pro messaged · 4:32 left", the pro's choice
  when it lands, and an **en-route lock badge** on the booking.
- Seed: add `contact_email` to seeded pros; add a customer-waiting scenario; add a small
  script to simulate each of the four pro replies (updates `provider_responses`); add a
  cross-ticket race case (an `en_route` booking + an incoming refund ticket → blocked to
  human).
- The Vercel demo frontend (`yesmadam-ops`) mirrors the new states as a fast follow-up.

## Judgment calls (production robustness)

1. **`stand_down` reuses the proven `execute_resolution(assign_replacement)`** with its
   built-in refund fallback, rather than two divergent timeout/can't-make-it policies.
   Replacement-when-available (preserves current live behavior), refund otherwise; the
   customer is always made whole.
2. **`provider_reply` is write-isolated from `provider_responses`** to make re-entry
   impossible (no event-loop risk).
3. **The customer leg of the reschedule offer also carries the 5-minute SLA** (no reply →
   declined → resolve), so a ticket can never get stuck waiting forever.

## Edge cases

- Pro has no `contact_email` → alert degrades (logged); SLA sweeper resolves after timeout.
- No replacement available on `stand_down` → full refund (existing `_pick_replacement`
  returns `None`).
- Booking already `cancelled`/`completed` when a reply arrives → `provider_reply` guard
  no-ops + stand-down notice to the pro.
- Duplicate alerts (two waiting tickets, same booking) → `alert_provider` idempotency
  links the second ticket to the open response, no second alert.
- `on_site` false-complaint → human review with proof-of-service; refund stays locked.
- `proposed_new_time` missing/in the past for a reschedule → validated in
  `apply_reschedule`; invalid → fall back to `stand_down`.

## Components touched (summary)

| Kind | Item | Change |
|---|---|---|
| Table | `provider_responses` | **new** |
| Table | `bookings` | add `provider_state` |
| Table | `professionals` | add `contact_email` |
| Table | `tickets` | add `awaiting_provider` status |
| Function | `alert_provider` | **new** |
| Function | `notify_provider` | **new** |
| Function | `sweep_provider_sla` | **new** |
| Function | `stand_down` | **new** |
| Function | `verify_service` | return `provider_state` |
| Function | `execute_resolution` | reused as-is (replacement→refund fallback) |
| Workflow | `provider_reply` | **new** (event: `provider_responses` UPDATE) |
| Workflow | `handle_ticket` | new `alert_provider` branch + refund-lock gate rule |
| Schedule | `provider-sla` | **new** (cron; verify support first) |
| App | `ops-queue` | surface `awaiting_provider` + en-route lock badge |
| Seed | `seed.sh` | pro emails, waiting scenario, reply simulator, race case |

## Non-goals

- Real two-way SMS/WhatsApp (modeled now; the row shape supports a later webhook swap).
- A provider-facing app or provider auth/identity.
- Customer negotiation beyond a single reschedule accept/decline.
- Wiring the Vercel frontend to live pod data (separate follow-up).
