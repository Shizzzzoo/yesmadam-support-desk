# YesMadam Support Desk — an agent that *runs* the support queue

**Ship to Get Hired — Gappy AI Hackathon · built on the Lemma SDK**
Live pod: https://support-desk-ops.apps.lemma.work

---

## The one line

A support/ops agent at an at-home services marketplace (YesMadam-style: salon &
wellness at home) drowns in repetitive, time-critical tickets. **We built an agent that
runs the queue end-to-end** — it classifies each ticket, checks the policy, finds the
booking, and **takes the real action** (reschedule, refund, replacement) on its own,
escalating only the genuinely hard cases to a human. It does the work of operating
support; it is not a chatbot.

## The problem (real-world fit)

Picture one ops agent's day: a stream of messages across WhatsApp, app chat, and email —
"my beautician hasn't shown up," "move my facial to 6 PM," "cancel and refund me." For
each, they read it, figure out what it is, open the booking system, check the policy
(refund-eligible? inside the free-reschedule window?), check availability, and type a
reply. Four or five lookups, hundreds of times a day.

Three things make this genuinely painful, not just annoying:

1. **Repetition without escape** — ~70–80% of tickets are the same 4–5 types; human
   judgment is only needed on the weird tail.
2. **A ticking clock** — the customer is physically waiting at home. A slow reply isn't
   bad service, it's a ruined appointment, a 1-star review, and a refund the company eats.
3. **Scattered context + inconsistent answers** — booking, policy, and availability live
   in different places, so every ticket is a hunt, and two agents give two different
   answers to the same refund.

**Scope we deliberately chose:** the internal ops tool that processes the inbound queue —
one user, one workflow. We are *not* rebuilding YesMadam's booking engine, the
beautician-matching algorithm, or a customer-facing bot.

## What it does — the loop (this is the whole product)

```
new ticket ──▶ triage agent: classify · find booking · check policy · draft reply
           ──▶ structural gate (deterministic, not the model's self-confidence):
                 auto-resolvable?  →  take the real booking action  →  ticket auto-resolved
                 not sure / risky? →  human-approval form  →  act on their decision
```

The agent **proposes**; deterministic functions **act**; a structural gate decides who's
allowed to act. When the desk resolves a reschedule, the **booking row actually changes**
(`scheduled → rescheduled`, new time written) and an audit event is logged — the line
between "does the work" and "talks about the work."

## Product judgment (the decisions we defend)

- **Real actions, not drafts.** Every resolution mutates the `bookings` table through a
  Python function and writes an audit trail. The differentiator is demonstrable, not
  claimed.
- **Structural gates, not vibes.** What the agent may do alone is decided by hard rules —
  the four real ticket types, confidence ≥ 0.8, a matched booking, and a **₹1,500 refund
  cap**. Above the cap, or anything ambiguous/multi-issue, escalates by design. We don't
  trust an LLM's self-reported confidence with money.
- **Escalation is a feature.** A messy or low-confidence ticket routing to a human is the
  system working, not failing.
- **Anti-fraud / proof-of-service (the standout).** A refund is decided on *verifiable
  proof of what happened*, never the customer's claim. Before any refund, a deterministic
  `verify_service` check reads the booking's **arrival check-in, start/completion OTP,
  work status, and service photos**. If a customer asks to "cancel and refund" a job the
  provider already started or finished, the refund is **auto-blocked** and routed to a
  human dispute review with the evidence attached — stopping a "sneaky cancel" after the
  work was done. Refunds are also prepaid-aware: money only moves when the booking was
  prepaid.

## Execution & proof (live, on the cloud)

Seeded with realistic data, the desk ran itself end-to-end:

- **Tickets auto-resolved on their own**, with the booking row visibly changed across
  *all three* action types — reschedules, refunds, **and** an auto-assigned replacement
  professional for a no-show.
- **Escalations parked correctly** in a human-approval inbox: both over-cap refunds, a
  compound ticket, an off-policy sales question, and a no-booking customer.
- **The anti-fraud gate, proven by name.** A "sneaky cancel" — a prepaid massage that was
  *in progress*, provider checked in, start-OTP verified, ₹999 (under the cap, so it
  *would* have auto-refunded) — was intercepted: the run's gate matched
  `proposed_action=='refund' && verify_service.service_proven`, the refund was **blocked**,
  the booking left untouched, and the ticket parked for a human with the evidence.

A live **operator app** shows the queue, each ticket's agent decision, the linked booking
row (with the 🛡 proof-of-service panel), an approval inbox, and an auto-resolution metric.

## Lemma SDK utilisation (every primitive, meaningfully)

| Primitive | How we use it |
|---|---|
| **Tables** (shared) | `bookings` (the row the agent mutates), `tickets` (the queue), `ticket_events` (audit), `professionals`, `service_evidence` (proof-of-service) |
| **Files** (built-in RAG) | `/knowledge/support-policy.md` — the agent retrieves refund/reschedule/no-show + dispute rules |
| **Functions** (Python) | `apply_triage`, `verify_service` (deterministic anti-fraud), `execute_resolution` (the coordinated booking mutation + resolve + audit) |
| **Agent** (POD toolset) | `triage` — read-only judgment returning a rich structured decision the workflow routes on |
| **Workflow** (AGENT/FUNCTION/DECISION/FORM) | `handle_ticket` — triage → verify → structural+anti-fraud gate → auto-action OR human-approval form |
| **Schedule** (DATASTORE trigger) | new `tickets` row → `handle_ticket` |
| **App** (single-file HTML, live) | the operator queue — the product humans live in |

## What's real vs. what's an integration step (honest, and the hiring story)

Every action is a real Python function against real pod state. Two things touch systems we
don't own in a hackathon: **moving real money** (a payment-gateway refund) and the **real
YesMadam app/database**. Today our `bookings` table is a faithful stand-in, and refunds are
recorded, not wired to a live gateway; proof-of-service signals are modelled as fields a
provider app would emit. **The verification and decision logic — the actual product — runs
entirely in the pod.** The day YesMadam adopts it, `issue_refund` points at their payment
API and `bookings` at their database; the agent logic doesn't change. That's the build,
and it's the hiring pitch.

## 90-second demo script

1. **0–15s** — state the problem; open the queue showing tickets the agent already handled.
2. **15–45s** — open a reschedule/refund ticket: show the agent's decision, then the
   **booking row that changed** + the audit trail. "No human touched this."
3. **45–70s** — open the **sneaky-cancel** ticket: the booking shows 🛡 proof of service;
   the refund is **blocked** and waiting in the dispute inbox with the evidence.
4. **70–90s** — the metric banner: auto-resolved vs. escalated. Close on the one line.
