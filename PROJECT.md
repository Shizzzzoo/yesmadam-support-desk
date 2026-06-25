# YesMadam Support Desk — Lemma Hackathon Project

**Living doc.** Update a section + add a changelog row every time we add implementation,
infrastructure, or feasibility detail. Don't rewrite locked sections without reason.

| Date | Change |
|---|---|
| 2026-06-19 | Problem statement locked; scope boundary + judging alignment set |
| 2026-06-19 | Six judge objections + answers captured |
| 2026-06-19 | Six implementation barriers + mitigations captured |
| 2026-06-22 | Lemma SDK introspected from PyPI — core primitives confirmed |
| 2026-06-24 | **Build day.** Platform repo cloned + SDK installed. Infra + data model grounded against the *real* `lemma-builder` references (not memory). Doc moved to disk. |
| 2026-06-24 | **Full pod bundle authored offline** at `./support-desk/` — all layers (tables, policy file, 2 functions, agent, workflow, schedule, HTML app), seed script (12 bookings, 7 pros, 16 tickets), payloads, README runbook. Every reference (functions/agents/workflows/schedules/apps/tables + 2 app-recipes) and the real TS SDK source read for exact shapes. All JSON/JSONC parses, both `code.py` compile, `seed.sh` parses. Ready to import Day-1. |
| 2026-06-24 | **Tuning VERIFIED live + email pipeline working (degrades gracefully).** Throttle was transient; once it cleared: Vivaan's no-show now `no_show` 0.95 → auto-resolved (replacement assigned), Saanvi's timing Q now `where_is_pro` 0.95 → auto-resolved (both previously mis-escalated). Auto-resolution rate ↑ to ~61%. New ticket #27 (Aarav reschedule) ran the full pipeline incl. the `notify` step, which **correctly degraded** (`ACCOUNT_RESOLUTION_ERROR: no account connected`) without breaking the run — email will actually send once a Gmail account is connected via the web UI. |
| 2026-06-24 | **No-show replacement hardened & verified.** `_pick_replacement` now excludes the no-show pro case/space-insensitively + a same-name guard (falls back to full refund if no *different* pro); action text reads "Replacement X assigned (was Y, no-show)". Verified: Vivaan's fresh no-show → **Karan Malhotra** assigned (was Pooja). The earlier "same pro" was test-data ping-pong from repeated runs, not a single-run bug. |
| 2026-06-24 | **Agent tuned + email-send built (import OK; live-verify was blocked by runtime throttle).** Triage instruction rewritten with a per-category rubric (trigger phrases, no_show vs where_is_pro, anti-ambiguous discipline) + confidence calibration (≥0.85 on clear single-intent). New `notify_customer` function + workflow `notify` node (both resolved paths → email) + `customer_email` field; `workspace-gmail` auth-config created; demo bookings' email set to the user's. All imported. **Blocked:** (1) cloud agent execution stalled mid-session — schedule fires but new tickets stay `new`, daemon connected-but-idle, direct `agents run` hangs → looks like free-tier model-runtime throttling after ~25 agent runs; (2) Gmail account OAuth can't be minted via CLI (`connect-requests create` has a `sync_detailed()` TypeError bug) — connect Gmail via the web UI instead. Tuning is authored+sound but not yet re-verified live; email path untested pending a connected Gmail account + a working runtime. |
| 2026-06-24 | **Anti-fraud / proof-of-service added & proven live.** New `service_evidence` table + proof fields on `bookings` (`payment_status`, `refund_status`, `check_in_at`, `start_otp_verified`, `completion_otp_verified`); new deterministic `verify_service` function; workflow gets a verify step + a **dispute gate rule** (`proposed_action=='refund' && service_proven` → human review, refund blocked); `execute_resolution` now prepaid-aware; app booking card shows the 🛡 proof block + refund status. Seeded a "sneaky cancel" (prepaid massage in-progress, checked-in, OTP-verified, ₹999 < cap): agent classified `cancel_refund`, gate matched the dispute rule **by name**, refund blocked, booking untouched, parked for human with evidence. |
| 2026-06-24 | **LIVE ON CLOUD (lemma.work).** Pod imported into "An Agetic Helpdesk for Yesmadam Platform Pod" (org "sahl's Space"). Day-1 spike passed (function mutated a booking). Caught + fixed 2 real bugs: `ticket_events` grant needed `table.read`; gate wrongly required `action != none` (broke `where_is_pro` auto-resolve) — now whitelists the 4 real categories. Seeded + ran end-to-end: **8/15 auto-resolved, 7 bookings changed autonomously, 7 escalations parked at the human-approval form**. Agent runs on built-in `system:lemma` runtime (no Claude Code daemon needed → pod runs unattended). App live at https://support-desk-ops.apps.lemma.work |

---

## 1. Problem Statement (LOCKED)

**User:** a support/ops agent at YesMadam (home-services marketplace — salon/wellness at home).

**Their day:** a constant stream of inbound messages across WhatsApp, in-app chat, and
email. "My beautician hasn't shown up." "Move my facial from 4pm to 6pm." "Cancel and
refund me." For each one they: read it → figure out what it is → open the booking system
→ check policy (refund-eligible? inside free-reschedule window?) → check availability →
type a reply. Four or five lookups, hundreds of times a day.

**Three things make it genuinely painful (not just annoying):**
1. **Repetition without escape** — ~70–80% of tickets are the same 4–5 types
   (reschedule, cancel/refund, no-show, "where's my pro"). Human judgment is only
   needed on the weird 20%.
2. **A ticking clock** — a customer is physically waiting at home; a slow reply isn't
   bad service, it's a ruined appointment + a 1-star review + a refund the company eats.
3. **Scattered context + inconsistent answers** — booking, policy, availability live in
   different places; two agents give two different answers to the same refund request.

**One sentence:**
> Support agents burn most of their day manually triaging and resolving a high volume of
> repetitive, time-sensitive tickets that follow predictable patterns — we build an agent
> that handles the predictable bulk end-to-end, so humans only ever touch the hard cases.

**The reframe that fits Lemma (not a chatbot):** the agent doesn't *answer questions*, it
**runs the queue** — receives a ticket, classifies it, pulls the booking, checks policy,
**takes the real action** (reschedule/refund against the booking record), updates status,
and escalates the messy ones. It *does the work of operating support*.

## 2. Scope Boundary (defend this — restraint is graded)

**We are NOT building:** YesMadam's booking engine, the beautician-matching algorithm, a
customer-facing bot, or real WhatsApp/email integration. **We ARE building:** the internal
ops tool that processes the inbound support queue — one user, one workflow.

In scope for auto-resolution: the top 4 ticket types. Everything else → escalate to human.
**Ambiguous / multi-issue → escalate is a feature, not a failure.**

## 3. Judging Alignment

| Axis | Weight | How we win it |
|---|---|---|
| Problem clarity & real-world fit | 35% | Specific user + concrete painful workflow, niched to a real partner (YesMadam). One real validation quote in the writeup. |
| Product judgment | 25% | Defended scope ("top 4 types, escalate the rest"), structural escalation gates, restraint. |
| Execution quality | 25% | Clean end-to-end loop, fully demoable, the booking row visibly changing. |
| Lemma SDK utilisation | 15% | Uses every primitive *meaningfully*: tables, files(RAG), functions, agent, workflow w/ human approval, schedule, app. |

**Hiring angle:** this is basically a YesMadam internal tool — their reviewer sees their own
problem solved. Submission writeup doubles as a product memo (problem → loop → why this
design → Lemma usage). Demo video: core loop on real input, <2 min, payoff in first 15s.

## 4. Judge Objections & Answers (= scoping-rationale draft)

1. **"Does it actually do the work, or just draft text?"** → It calls `reschedule_booking` /
   `issue_refund` **functions** that mutate the `bookings` table. The demo shows the booking
   row changing, not just a drafted message. *(Baked into the data model — see §6.)*
2. **"Why not Zendesk AI / Intercom Fin?"** → Domain-specific *actions* + time-critical
   escalation logic. Generic tools answer from a help center; ours knows what a "no-show"
   means operationally, checks live booking + availability, and escalates a stranded-customer
   ticket differently from a billing one. It's an **ops tool for a physical-services
   marketplace**, not a support bot.
3. **"You haven't talked to anyone."** → Before submission, get ONE quote from anyone who's
   done marketplace/delivery support (Urban Company, Swiggy, a salon chain): "most repetitive
   ticket type + what slows you down." Turns "I assumed" into "I validated." *(TODO)*
4. **"Most crowded pick."** → Niche loudly + early: physical-services marketplace, real
   booking actions, time-pressure. That separates us from 40 generic startup support desks.
5. **"Where's the proof it's better?"** → Instrument the demo: "23/30 auto-resolved, 7
   escalated" + before/after handle time. A visible metric reads as product maturity.
6. **"Classification face-plants on messy tickets."** → "ambiguous / multi-issue → escalate"
   is a first-class intended outcome. A messy ticket routing to a human = feature working.

## 5. Infrastructure: Lemma (VERIFIED against the cloned platform repo, 2026-06-24)

Lemma = open-source workspace where humans + agents share one **pod** (tables, files,
functions, agents, workflows, schedules, connectors, surfaces, apps under one permission
boundary). **A pod is just a directory of files** → we author the whole bundle offline, then
`lemma pods import`. The intended build path *is* a coding agent (us) + the `lemma-builder`
skill. This kills the old "barrier #1: we don't know what Lemma can do."

**Run locally (needs Docker/Podman + a model key):**
```bash
curl -fsSL https://raw.githubusercontent.com/lemma-work/lemma-platform/main/install.sh | bash
# app: http://127-0-0-1.sslip.io:3711  api: :8711  (use that host, NOT localhost)
lemma-stack config set LEMMA_DEFAULT_MODEL_TYPE anthropic_compat
lemma-stack config set LEMMA_ANTHROPIC_API_KEY sk-ant-...
lemma-stack restart
uv tool install lemma-terminal
lemma servers select local && lemma auth login
```
Or use the hosted **lemma.work** cloud (same stack, nothing to host).

**Primitive → our use:**
| Lemma primitive | Our support desk uses it for |
|---|---|
| **Tables** (shared, `enable_rls:false`) | `tickets` queue, `bookings` (the thing the agent mutates), `ticket_events` audit, `professionals` |
| **Files** (`/knowledge`, built-in RAG) | `support-policy.md` — agent retrieves refund/reschedule/no-show rules |
| **Functions** (Python, server-side) | the real actions: `reschedule_booking`, `issue_refund`, `assign_replacement`, `resolve_ticket` |
| **Agent** (POD toolset) | `triage` — classify + retrieve policy + decide + call action |
| **Workflow** (AGENT/DECISION/FUNCTION/FORM/WAIT) | `handle_ticket` — orchestrates triage → gate → action OR human approval (FORM node assigned to ops member) |
| **Schedule** (DATASTORE trigger) | new `tickets` row → start `handle_ticket` workflow |
| **App** (single-file HTML, `watchChanges`) | the operator queue UI — the hero screen |

**Build order (per lemma-builder):** tables → files → functions → agents → workflows →
schedules → app → seed. Verify each layer with real data before the next.

## 6. Data Model (DRAFT — grounded in references/tables.md)

> All work tables are **shared** (`enable_rls:false`) — it's a team queue. System columns
> (`id` UUIDv7, `created_at`, `updated_at`) are automatic — never declared.

**`bookings`** (the system the agent ACTS on — differentiator):
`code`(SERIAL auto), `customer_name`(TEXT), `service`(ENUM haircut/facial/massage/manicure),
`professional_name`(TEXT), `scheduled_at`(DATETIME), `status`(ENUM
scheduled/in_progress/completed/cancelled/no_show/rescheduled), `amount`(FLOAT),
`address`(TEXT).

**`tickets`** (the queue — unit of work):
`number`(SERIAL auto), `customer_name`(TEXT), `channel`(ENUM whatsapp/app_chat/email),
`raw_message`(TEXT req), `booking_id`(UUID FK bookings.id — agent links it),
`category`(ENUM reschedule/cancel_refund/no_show/where_is_pro/other/ambiguous, default
ambiguous), `urgency`(ENUM low/normal/high/urgent), `status`(ENUM
new/triaged/auto_resolved/waiting_approval/escalated/resolved, default new),
`agent_decision`(JSON — classification+reasoning+proposed action), `draft_reply`(TEXT),
`confidence`(FLOAT), `run_id`(TEXT — jump to workflow run).

**`ticket_events`** (audit trail — proves "it did the work"):
`ticket_id`(UUID FK tickets.id req), `kind`(ENUM
created/classified/action_taken/escalated/approved/resolved), `note`(TEXT),
`actor`(TEXT — agent vs human).

**`professionals`** (light — availability for reschedule/no-show matching; optional):
`name`(TEXT), `services`(JSON), `available_slots`(JSON), `area`(TEXT).

**`/knowledge/support-policy.md`** — refund eligibility, free-reschedule window, no-show
compensation rules, escalation thresholds.

**Structural escalation gates (the confidence fix — don't trust model self-confidence):**
- refund amount > ₹[threshold] → always human approval (WAIT/FORM)
- `category` ∈ {ambiguous, other} → escalate
- multi-issue detected → escalate
- `confidence` < [threshold] → escalate
- no matching booking found → escalate

## 7. Core Loop

```
new ticket row → schedule fires → handle_ticket workflow:
  AGENT(triage): read ticket → search /knowledge policy → find booking → classify + decide
  DECISION: passes structural gates?
    YES → FUNCTION(reschedule_booking | issue_refund | assign_replacement)  → bookings row changes
        → resolve_ticket(status=auto_resolved, draft_reply)                  → ticket_event(action_taken)
    NO  → FORM(assigned to ops member): show classification + draft + booking → human approve/edit
        → on submit: FUNCTION action → resolve (status=resolved)             → ticket_event(approved)
```
App shows: queue (by status) → ticket detail (classification, draft reply, linked booking
row) → approve button. `watchChanges` keeps it live. Metric banner: auto-resolved vs escalated.

## 8. Build Plan (June 24–30)

- **DONE — offline authoring (no stack needed):** the full pod bundle is authored at
  `./support-desk/`. Tables (bookings/tickets/ticket_events/professionals, all shared),
  `/knowledge/support-policy.md`, functions `apply_triage` + `execute_resolution` (the
  reliable verb that mutates the booking + resolves + logs), `triage` agent (read-only,
  rich output_schema), `handle_ticket` workflow (triage → apply_triage → structural gate →
  auto action OR human-approval FORM), `new-ticket` DATASTORE schedule, the `ops-queue`
  HTML app (queue · decision · **linked booking row that visibly changes** · approval inbox ·
  metric banner), `seed/seed.sh`, payloads, README runbook. Validated offline.
- **Stack up (needs USER):** Docker/Podman + model API key → `install.sh` → `lemma auth login`.
- **Import + test each layer:** `lemma pods import ./support-desk --dry-run` then real;
  `lemma pods doctor`; then `lemma functions run` / `lemma agents run` / `lemma workflows
  validate` per the README "Verify each layer" runbook.
- **Day-1 spike (smallest possible):** `execute_resolution` updates one booking record →
  confirms the differentiator. Exact commands in `support-desk/README.md`.
- **Then seed** (`bash support-desk/seed/seed.sh`) so the pod demos itself, deploy the app.
- **Polish:** the app screen legible; the metric banner already instrumented (auto-resolution rate).
- **29th:** record demo + write submission (product memo). **30th:** submit by midday.

## 9. Open Questions / Blockers

- [ ] **USER (now the only real blocker to importing):** Docker or Podman installed? Model
      API key (Anthropic/OpenAI) available — or use hosted lemma.work cloud instead of self-host?
- [x] Refund ₹ threshold + confidence threshold — **set: refund auto-cap ₹1,500, confidence ≥ 0.8.**
      Written into both the policy doc and the workflow gate so they stay consistent.
- [ ] One validation quote from a marketplace-support person (objection #3).
- [ ] Team size — solo or 2–3?
- [x] Exact function/agent/workflow/schedule/app JSON shapes — **confirmed against all
      lemma-builder references + the real TS SDK source; bundle authored and validated offline.**

### Day-1 re-checks (SDK is fresh — verify, don't assume) — see `support-desk/README.md`
- [ ] `lemma workflows validate` accepts the JMESPath gate (`&&`, backtick literals).
- [ ] DATASTORE trigger exposes the new id at `start.metadata.record_id`.
- [ ] App's `workflows.runs.waitingAssignedToMe()` returns the **unassigned** FORM waits;
      if not, assign `escalate_form` to an ops member and re-import.
- [ ] `agent_decision` JSON round-trips for the app to render reasoning.
```
