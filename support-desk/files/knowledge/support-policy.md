# YesMadam-style At-Home Services — Support Desk Policy

This is the single source of truth the support desk follows. The triage agent must
retrieve and apply these rules; the workflow enforces the hard escalation thresholds.

## Service categories the desk handles

1. **reschedule** — customer wants to move an existing booking to a different time.
2. **cancel_refund** — customer wants to cancel and get money back.
3. **no_show** — the professional did not arrive (or left early); customer is stranded.
4. **where_is_pro** — customer is asking for an ETA / live status of their professional.

Anything that is not clearly one of these four → **other**. Anything that mixes
multiple issues, is unclear, or asks for something off-policy → **ambiguous**.
Both `other` and `ambiguous` are **always escalated to a human** — that is intended,
not a failure.

## Reschedule rules

- **Free reschedule window:** a booking may be rescheduled **free of charge** if the
  request comes in **more than 3 hours before** the scheduled start time.
- Inside 3 hours, a reschedule fee may apply — this requires **human approval**.
- A reschedule sets the booking to `rescheduled` with the new `scheduled_at`.
- Never reschedule to a time in the past.

## Cancellation & refund rules

- **Full refund** if cancelled **more than 6 hours before** the start time.
- **50% refund** if cancelled between 6 hours and 1 hour before start.
- **No refund** inside 1 hour of start (the professional is already en route).
- **Refund auto-approval cap: ₹1,500.** The agent may auto-issue a refund only when the
  refundable amount is **₹1,500 or less**. Any refund **above ₹1,500 must be approved
  by a human** — no exceptions.
- A no-show (below) always qualifies for a **full refund** regardless of timing.

## No-show rules

- If the professional did not arrive within **15 minutes** of the slot, it is a
  **no_show**: the customer is owed a **full refund OR a replacement professional**,
  their choice.
- Prefer offering a **replacement** when one is available in the same area and service;
  fall back to a full refund.
- A no-show is **high urgency** — a customer is physically waiting.

## "Where is my professional" rules

- Reassure with the booking's current status and professional name. This is an
  informational reply — **no booking change** is made.
- If the slot start time has already passed by more than 15 minutes, treat it as a
  **no_show** instead.

## Urgency guidance

- **urgent / high:** customer is currently waiting (no_show, where_is_pro near/after
  start time, same-day reschedule).
- **normal:** future-dated reschedule, non-time-critical refund.
- **low:** general questions.

## Escalation thresholds (the desk's hard gates)

A ticket is auto-resolved by the agent **only if ALL hold**:

1. category is one of {reschedule, cancel_refund, no_show, where_is_pro},
2. a matching booking was found,
3. classification confidence ≥ 0.8,
4. for refunds, the refundable amount ≤ ₹1,500.

If any fails → **escalate to a human** for review and approval. When in doubt, escalate.

## Disputed cancellations & proof of service (anti-fraud)

A refund must be decided on **verifiable proof of what happened**, never on the
customer's claim alone. Before any refund, the desk checks the booking's proof-of-service
signals — provider **arrival check-in**, **start/completion OTP**, **work status**
(`in_progress`/`completed`), and any **service photos**.

- If a customer requests a refund but the booking shows **proof the service was rendered**
  (checked in, OTP verified, in progress/completed, or photos on file), the refund is
  **auto-blocked** and the ticket is sent to a **human dispute review** with all the
  evidence attached. The agent never auto-refunds a job that has proof of service —
  this stops "sneaky cancels" after the work is done.
- A refund only auto-issues when there is **no** proof of service (the provider had not
  started) **and** the normal refund rules + ₹1,500 cap are satisfied.
- **Prepaid vs pay-after:** a refund only moves money when `payment_status` is `prepaid`.
  A `pay_after` cancellation just closes the booking — there's nothing to refund.

## Reply tone

Warm, brief, specific. Name the professional and the new time/amount. Apologise once
for any disruption; do not over-apologise. Always state the concrete outcome
("I've rescheduled your facial to 6:00 PM today" / "I've issued a full ₹999 refund").
