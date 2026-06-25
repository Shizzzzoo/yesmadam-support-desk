# YesMadam Support Desk — Lemma Hackathon

An agentic support desk for an at-home services marketplace (YesMadam-style: salon &
wellness at home). An **agent runs the inbound ticket queue** — it classifies each
ticket, pulls the booking, checks policy, **takes the real action** (reschedule / refund
/ replacement) against the booking record, and escalates the hard cases to a human. It
does the work of operating support; it is not a chatbot.

## Repository layout

| Path | What it is |
|---|---|
| `support-desk/` | The Lemma **pod bundle** — tables, functions, agent, workflows, schedules, the ops app, and the seed script. This is the product. Import with `lemma pods import ./support-desk`. |
| `yesmadam-ops/` | A hand-themed **Vite + React** marketing/demo frontend (deployed to Vercel at `yesmadam-ops.vercel.app`), seeded with a real snapshot of pod data. |
| `docs/superpowers/` | **Specs and implementation plans** (e.g. the provider-coordination loop design + plan). |
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

## Local checks (pod bundle)

```bash
cd support-desk && bash tests/run.sh   # JSONC validity, py_compile, pure-logic unit tests
```

> The `lemma-platform/` clone and all `node_modules/` are intentionally git-ignored.
