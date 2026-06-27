# YesMadam Support Desk — an agent that *runs* the support queue

**Ship to Get Hired — Gappy AI Hackathon · built on the Lemma SDK**
Live operator app (in-pod): https://support-desk-ops.apps.lemma.work
Live customer chat (in-pod): https://yesmadam-chat.apps.lemma.work
Live demo UI (Vercel): https://yesmadam-ops.vercel.app

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

- **Provider coordination — the two-sided loop (the second standout).** A no-show or
  "where's my pro" means a customer is *physically waiting*, so the desk doesn't just
  refund — it **proactively pings the assigned professional** ("a client is waiting")
  and lets their reply drive the outcome: *running late* (ETA reassures the customer, the
  booking is **held** under an **en-route lock**), *reschedule* (offer the customer a new
  slot), *can't make it* (replacement, refund fallback), or *on-site* (route to a human as
  a likely false alarm). If the pro stays silent past a **5-minute SLA**, the customer is
  **auto-refunded/replaced** — they never chase it. Crucially, the en-route lock is a
  **cross-ticket guard**: a separate "just cancel and refund me" ticket on a booking whose
  pro is already on the way is **blocked** and parked for a human, so a refund can never
  fire out from under a committed professional. The whole loop runs on Functions +
  Workflows + a time Schedule — no agent at all once the alert is sent — so it's reliable.

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

- **Concierge — the conversational customer front door (verified live).** Beyond the
  ops-side queue runner, a customer can now self-serve in plain language. A multi-turn
  `concierge` agent answers from the customer's *actual* booking ("why is my pro late?" →
  reads check-in/en-route state) and policy, **asks clarifying questions** (refund vs
  replacement, which booking), and on confirmation **hands off** to the same engine, then
  reports the real outcome back in chat. It is **answer-only / read-only on bookings** — it
  never moves money; it just files a ticket, and the engine's gates decide everything
  downstream. Proven end-to-end on the cloud: a 3-turn chat ("cancel my manicure and refund
  me" → confirm → "did it go through?") drove a real **cancellation + full ₹699 refund**,
  with the booking row changed and the result relayed truthfully. A live **customer chat
  app** hosts it.

## Lemma SDK utilisation (every primitive, meaningfully)

| Primitive | How we use it |
|---|---|
| **Tables** (shared) | `bookings` (the row the agent mutates, incl. the `provider_state` en-route lock), `tickets` (the queue), `ticket_events` (audit), `professionals`, `service_evidence` (proof-of-service), `provider_responses` (the coordination loop) |
| **Files** (built-in RAG) | `/knowledge/support-policy.md` — the agent retrieves refund/reschedule/no-show + dispute rules |
| **Functions** (Python) | `apply_triage`, `verify_service` (deterministic anti-fraud), `execute_resolution` (booking mutation + resolve + audit); the coordination set: `alert_provider`, `notify_provider`, `read_response`, `commit_en_route`, `offer_reschedule`, `apply_reschedule`, `stand_down`, `provider_stand_notice`, `sweep_provider_sla`; and `file_ticket` (the concierge → queue hand-off) |
| **Agents** | `triage` — read-only judgment returning a rich structured decision the workflow routes on; `concierge` — multi-turn customer chat (POD + USER_INTERACTION toolsets), read-only on data + policy RAG, asks clarifying questions, files a ticket on confirmation |
| **Workflows** (AGENT/FUNCTION/DECISION/FORM) | `handle_ticket` (triage → verify → structural+anti-fraud+en-route gate → auto-action / alert-pro / human form), `provider_reply` (routes the pro's reply), `sweep_sla` (cron SLA sweep) |
| **Schedules** | DATASTORE: new `tickets` → `handle_ticket`, `provider_responses` UPDATE → `provider_reply`; **TIME (cron)**: every minute → `sweep_sla` (the 5-min SLA) |
| **Conversations** (multi-turn) | the `concierge` chat — context carried across turns, clarifying questions via the user-interaction tool, gated tool-calls routed through grants |
| **Notifications** | recorded in-pod (`ticket_events`) and surfaced in the app — reliable, no external account; the delivery channel is pluggable (drop in an API-key connector like Twilio/Resend for real SMS/email without changing the workflow) |
| **Apps** (single-file HTML, live) | `ops-queue` — the operator console; `customer-chat` — the customer-facing concierge chat |

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

> Run it on the live demo UI (`yesmadam-ops.vercel.app`) — it opens on the live
> coordination ticket. Drop to the in-pod app for the booking-row mutations if you want.

1. **0–12s — the problem.** "A customer is waiting at home and the pro hasn't shown.
   Today an ops agent juggles 4–5 lookups per ticket, hundreds a day." Open the queue.
2. **12–35s — pro pinged → running late.** Open the **no-show** ticket: the assistant
   classified it and **messaged the assigned pro** ("client waiting"). Show the Provider
   Coordination panel — the pro replied *"running late, 15 min"*, the booking is **held
   under the en-route lock**, and the customer got an automatic ETA reassurance. *No
   refund, no cancel — the appointment is saved.*
3. **35–55s — pro silent → auto-refund/replace.** Open the ticket where the pro **never
   replied**: the **5-minute SLA expired**, the pro was stood down, and the customer was
   **made whole automatically** (replacement assigned) — they never had to chase it.
4. **55–72s — the race guard (the kicker).** Open the **"just cancel and refund me"**
   ticket on a booking whose pro is already *en route*. ₹1,299 is under the auto-refund
   cap, so it *would* have refunded — but the **en-route lock blocked it** and parked it
   for a human, so we never cancel out from under a committed pro. (Same mechanism that
   blocks the **sneaky-cancel** on a service-proven booking — the 🛡 anti-fraud beat.)
5. **72–90s — the proof.** The metric banner: auto-resolution rate, pros coordinated,
   refunds protected. Close on the one line — *"it runs the queue; humans only touch the
   hard cases."*
