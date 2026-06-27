# YesMadam Support Desk — Lemma Hackathon

An agentic support desk for an at-home services marketplace (YesMadam-style: salon &
wellness at home). An **agent runs the inbound ticket queue** — it classifies each
ticket, pulls the booking, checks policy, **takes the real action** (reschedule / refund
/ replacement) against the booking record, and escalates the hard cases to a human. It
does the work of operating support.

Three layers, all live on the cloud pod:
1. **The engine** — `handle_ticket` triages a ticket and takes the real booking action
   within hard gates (refund cap, anti-fraud proof-of-service, escalation).
2. **Provider coordination** — when a customer is waiting, it pings the assigned pro and
   lets their reply (or a 5-min SLA) drive the outcome, with an en-route refund lock.
3. **Concierge** — a conversational customer front door: the customer chats, it answers
   from their booking, asks clarifying questions, and hands off to the engine to resolve.

## Live links

| Surface | URL |
|---|---|
| Ops console (in-pod app) | https://support-desk-ops.apps.lemma.work |
| Customer chat (in-pod app) | https://yesmadam-chat.apps.lemma.work |
| Demo UI (Vercel) | https://yesmadam-ops.vercel.app |

## Repository layout

| Path | What it is |
|---|---|
| `support-desk/` | The Lemma **pod bundle** — tables, functions, agents (`triage` + `concierge`), workflows, schedules, the ops + customer-chat apps, and the seed script. This is the product. Import with `lemma pods import ./support-desk`. |
| `yesmadam-ops/` | A hand-themed **Vite + React** marketing/demo frontend (deployed to Vercel at `yesmadam-ops.vercel.app`), seeded with a real snapshot of pod data. |
| `docs/superpowers/` | **Specs and implementation plans** (provider-coordination loop + concierge front door). |
| `PROJECT.md` | Living design doc — problem statement, judging alignment, build changelog. |
| `SUBMISSION.md` | Hackathon submission write-up. |
| `scratch-snapshot/` | Exported JSON snapshot of live pod data used to seed the frontend. |

## Key feature: the provider-coordination loop

When a "customer-waiting" ticket (no-show / "where's my pro") arrives, the desk
proactively alerts the assigned professional, then lets their reply — *running late*,
*reschedule*, *can't make it*, *on-site* — or a 5-minute SLA timeout drive the
resolution. A `provider_state` lock on the booking blocks a refund-and-cancel from firing
out from under a committed pro (even from a different ticket). See
`docs/superpowers/specs/2026-06-25-provider-coordination-loop-design.md`.

## Key feature: the concierge (conversational customer front door)

A customer chats in plain language — *"why is my pro late?"*, *"can I get a refund?"* —
and the `concierge` agent answers from their actual booking + policy, asks clarifying
questions, and (on confirmation) files a ticket into the engine, which takes the real
action and reports the outcome back in chat. Concierge is **read-only on bookings** — it
never moves money itself; every refund/booking change still goes through the engine's
gates. Verified live end-to-end: a 3-turn chat resolved a real cancellation + full refund.
See `docs/superpowers/specs/2026-06-26-concierge-conversational-front-door-design.md`.

## Local checks (pod bundle)

```bash
cd support-desk && bash tests/run.sh   # JSONC validity, py_compile, pure-logic unit tests
```

> The `lemma-platform/` clone and all `node_modules/` are intentionally git-ignored.
