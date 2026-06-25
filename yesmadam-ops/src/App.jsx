import React, { useId, useMemo, useState } from "react";
import {
  allTickets,
  metrics,
  cases,
  providers,
  eventsFor,
  evidenceFor,
  thread,
  currentUser,
  SERVICE_ICON,
  CATEGORY_LABEL,
} from "./data/index.js";

/* ───────────────────────── formatting ───────────────────────── */
const IST = "Asia/Kolkata";
const fmt = (iso, opts) =>
  iso ? new Intl.DateTimeFormat("en-IN", { timeZone: IST, ...opts }).format(new Date(iso)) : "";
const fmtDateTime = (iso) =>
  fmt(iso, { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit", hour12: true });
const fmtTime = (iso) => fmt(iso, { hour: "numeric", minute: "2-digit", hour12: true });
const fmtDay = (iso) => fmt(iso, { day: "numeric", month: "short" });
const ago = (iso) => {
  const mins = Math.round((Date.parse("2026-06-24T17:10:00Z") - Date.parse(iso)) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const h = Math.round(mins / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
};
const inr = (n) => `₹${Number(n).toLocaleString("en-IN")}`;
const initials = (name = "") =>
  name.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();

const STATUS_LABEL = {
  auto_resolved: "Auto-resolved",
  resolved: "Resolved",
  triaged: "Needs human",
  escalated: "Escalated",
  waiting_approval: "Awaiting approval",
  new: "New",
};

/* ───────────────────────── the seal (signature) ───────────────────────── */
function Seal({ tone = "resolved" }) {
  const raw = useId();
  const id = "seal-" + raw.replace(/[^a-z0-9]/gi, "");
  const ring = tone === "blocked" ? "#E5484D" : "#E6007E";
  const wash = tone === "blocked" ? "#FDE7E7" : "#FFE6F3";
  const label =
    tone === "blocked" ? "PARKED • FOR HUMAN REVIEW • " : "RESOLVED • BY THE ASSISTANT • ";
  return (
    <svg viewBox="0 0 100 100" className="seal-svg" role="img" aria-label={label.trim()}>
      <defs>
        <path id={id} d="M50,50 m-35,0 a35,35 0 1,1 70,0 a35,35 0 1,1 -70,0" />
      </defs>
      <circle cx="50" cy="50" r="47" fill={wash} stroke={ring} strokeWidth="1.4" />
      <circle cx="50" cy="50" r="47" fill="none" stroke={ring} strokeWidth="2.4" strokeDasharray="0.5 4" strokeLinecap="round" opacity="0.55" />
      <circle cx="50" cy="50" r="29" fill="none" stroke={ring} strokeWidth="1" opacity="0.4" />
      <text fontSize="7.6" fontWeight="700" letterSpacing="1.6" fill={ring} style={{ fontFamily: "var(--mono)" }}>
        <textPath href={`#${id}`} startOffset="0%">{label.repeat(2)}</textPath>
      </text>
      {tone === "blocked" ? (
        <>
          <rect x="42" y="46" width="16" height="13" rx="2.5" fill="none" stroke={ring} strokeWidth="3" />
          <path d="M44.5 46v-3a5.5 5.5 0 0 1 11 0v3" fill="none" stroke={ring} strokeWidth="3" />
        </>
      ) : (
        <path d="M40 50.5l6.5 6.5L61 42" fill="none" stroke={ring} strokeWidth="4.5" strokeLinecap="round" strokeLinejoin="round" />
      )}
    </svg>
  );
}

/* ───────────────────────── small pieces ───────────────────────── */
const Badge = ({ kind, children }) => (
  <span className={`badge b-${kind}`}>
    <span className="dot" />
    {children}
  </span>
);

const ServiceIcon = ({ service }) => (
  <span className="svc-ico" aria-hidden>{SERVICE_ICON[service] || "🧴"}</span>
);

const NAV = [
  { key: "queue", label: "Queue", icon: "M4 6h16M4 12h16M4 18h10" },
  { key: "cases", label: "Cases", icon: "M4 5h16v14H4zM4 9h16" },
  { key: "providers", label: "Providers", icon: "M12 12a4 4 0 100-8 4 4 0 000 8zM5 20a7 7 0 0114 0" },
  { key: "messages", label: "Messages", icon: "M4 5h16v11H8l-4 4z" },
];

function Sidebar({ view, setView, counts }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="seal" aria-hidden>
          <Seal tone="resolved" />
        </span>
        <span className="name">
          YesMadam
          <small>Support Desk</small>
        </span>
      </div>
      <nav className="nav">
        {NAV.map((n) => (
          <a
            key={n.key}
            className={view === n.key ? "active" : ""}
            href={`#${n.key}`}
            onClick={(e) => { e.preventDefault(); setView(n.key); }}
          >
            <svg className="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d={n.icon} />
            </svg>
            <span>{n.label}</span>
            {counts[n.key] != null && <span className="count">{counts[n.key]}</span>}
          </a>
        ))}
      </nav>
      <div className="side-foot">
        <div className="live"><span className="pulse" /> Agent on duty</div>
        <p className="who" style={{ marginTop: 10 }}>
          Signed in as <b>{currentUser}</b>
        </p>
      </div>
    </aside>
  );
}

/* ───────────────────────── stats ───────────────────────── */
function Stats() {
  return (
    <div className="stats">
      <div className="stat hero">
        <div className="ring" />
        <div className="v">{metrics.rate}%</div>
        <div className="l">Auto-resolution rate</div>
      </div>
      <div className="stat">
        <div className="v">{metrics.autoResolved}</div>
        <div className="l">Resolved by assistant</div>
      </div>
      <div className="stat">
        <div className="v">{metrics.needsHuman}</div>
        <div className="l">Parked for a human</div>
      </div>
      <div className="stat">
        <div className="v">{metrics.bookingsActed}</div>
        <div className="l">Bookings acted on</div>
      </div>
      <div className="stat">
        <div className="v">{metrics.protected}</div>
        <div className="l">Refunds protected</div>
      </div>
    </div>
  );
}

/* ───────────────────────── queue card ───────────────────────── */
function QueueCard({ t, selected, onClick }) {
  const b = t.booking;
  const statusKind = t.status;
  return (
    <button className={`scard${selected ? " sel" : ""}`} onClick={onClick}>
      <div className="row1">
        <ServiceIcon service={b?.service} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="who">{t.customer_name}</div>
          <div className="num mono">#{t.number} · {b ? `booking #${b.code}` : "no booking"}</div>
        </div>
        <Badge kind={statusKind}>{STATUS_LABEL[t.status]}</Badge>
      </div>
      <div className="msg">{t.raw_message}</div>
      <div className="row3">
        <span className="badge b-channel"><span className="dot" />{t.channel}</span>
        <span className="chip">{CATEGORY_LABEL[t.category] || t.category}</span>
        {t.urgency === "high" && <span className="badge b-high"><span className="dot" />urgent</span>}
        <span className="pill" style={{ marginLeft: "auto" }}>{ago(t.created_at)}</span>
      </div>
    </button>
  );
}

/* ───────────────────────── booking transform (signature) ───────────────────────── */
function transformOf(t) {
  const b = t.booking;
  if (!b) return null;
  const action = t.agent_decision?.proposed_action;
  const la = b.last_action || "";

  if (action === "assign_replacement" || /Replacement/.test(la)) {
    const m = la.match(/Replacement (.+?) assigned(?: \(was (.+?), no-show\))?/);
    const newPro = m?.[1] || b.professional_name;
    const oldPro = m?.[2] || b.previous_professional || "Previous pro";
    return {
      kind: "Professional reassigned",
      before: { k: "Was", v: oldPro, sub: "Marked no-show" },
      after: { k: "Now", v: newPro, sub: "Replacement en route" },
    };
  }
  if (action === "reschedule" || /Rescheduled/.test(la)) {
    const m = la.match(/Rescheduled to ([0-9T:+\-.Z]+)/);
    const newTime = m?.[1];
    return {
      kind: "Appointment moved",
      before: { k: "Was", v: "Scheduled", sub: fmtDay(b.scheduled_at) },
      after: { k: "Now", v: newTime ? fmtTime(newTime) : "Rescheduled", sub: newTime ? fmtDay(newTime) : "Confirmed" },
    };
  }
  if (action === "refund" && (b.status === "cancelled" || /Cancelled/.test(la))) {
    const m = la.match(/₹([\d.,]+)/);
    return {
      kind: "Cancelled & refunded",
      before: { k: "Was", v: "Scheduled", sub: `${b.payment_status} · ${inr(b.amount)}` },
      after: { k: "Now", v: "Cancelled", sub: m ? `${inr(parseFloat(m[1].replace(/,/g, "")))} refunded` : "Full refund" },
    };
  }
  return null;
}

function BookingCard({ t }) {
  const b = t.booking;
  if (!b) return null;
  const xf = transformOf(t);
  const resolved = t.status === "auto_resolved" || t.status === "resolved";
  const proven = b.start_otp_verified || b.check_in_at || b.status === "in_progress";
  const disputeBlocked = t.category === "cancel_refund" && t.status === "triaged" && proven;
  const evid = evidenceFor(b.id);

  return (
    <div className="booking">
      {resolved && (
        <div className="seal-stamp" key={t.id}><Seal tone="resolved" /></div>
      )}
      {disputeBlocked && (
        <div className="seal-stamp" key={t.id + "b"}><Seal tone="blocked" /></div>
      )}

      <div className="bh">
        <ServiceIcon service={b.service} />
        <div>
          <div style={{ fontFamily: "var(--display)", fontWeight: 700, fontSize: 16, color: "var(--plum)", textTransform: "capitalize" }}>
            {b.service} · {b.customer_name}
          </div>
          <div className="code mono">BOOKING #{b.code}</div>
        </div>
      </div>

      {xf ? (
        <div className="transform">
          <div className="tstate before">
            <div className="tk">{xf.before.k}</div>
            <div className="tv">{xf.before.v}</div>
            <div className="tsub">{xf.before.sub}</div>
          </div>
          <div className="tarrow" aria-hidden>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </div>
          <div className="tstate after">
            <div className="tk">{xf.after.k}</div>
            <div className="tv">{xf.after.v}</div>
            <div className="tsub">{xf.after.sub}</div>
          </div>
        </div>
      ) : (
        <div className="transform" style={{ gridTemplateColumns: "1fr" }}>
          <div className="tstate">
            <div className="tk">Booking unchanged</div>
            <div className="tv" style={{ textTransform: "capitalize" }}>{b.status}</div>
            <div className="tsub">{fmtDateTime(b.scheduled_at)} · {b.professional_name}</div>
          </div>
        </div>
      )}

      <div className="kv2">
        <span className="k">Professional</span><span>{b.professional_name}</span>
        <span className="k">Scheduled</span><span className="mono">{fmtDateTime(b.scheduled_at)}</span>
        <span className="k">Address</span><span>{b.address}</span>
        <span className="k">Amount</span><span className="mono">{inr(b.amount)} · {b.payment_status}</span>
      </div>

      {(proven || disputeBlocked) && (
        <div className="proof" style={{ marginTop: 16 }}>
          <div className="ph">🛡 Proof of service on file</div>
          <ul>
            {b.check_in_at && <li>Pro checked in {fmtTime(b.check_in_at)}{b.check_in_geo ? ` · ${b.check_in_geo}` : ""}</li>}
            {b.start_otp_verified && <li>Start OTP verified by customer</li>}
            {evid.map((e) => <li key={e.id}>{e.note}{e.occurred_at ? ` · ${fmtTime(e.occurred_at)}` : ""}</li>)}
          </ul>
          {disputeBlocked && (
            <div className="pn">Refund request on a service-proven booking — auto-refund blocked by the dispute gate and parked for a human.</div>
          )}
        </div>
      )}

      {b.last_action && (
        <div className="last mono">↳ {b.last_action}</div>
      )}
    </div>
  );
}

/* ───────────────────────── timeline ───────────────────────── */
function Timeline({ ticketId }) {
  const events = eventsFor(ticketId);
  if (!events.length) return null;
  return (
    <div>
      <div className="block-label">Audit trail</div>
      <div className="timeline">
        {events.map((e) => (
          <div key={e.id} className={`tl-item${e.actor === "human" ? " human" : ""}`}>
            <span className="node" />
            <div className="kind">
              {e.kind.replace(/_/g, " ")}
              <span className={`tl-actor mono ${e.actor === "human" ? "human" : "agent"}`}>{e.actor}</span>
            </div>
            {e.note && <div className="note">{e.note}</div>}
            <div className="when mono">{fmtDateTime(e.created_at)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ───────────────────────── detail ───────────────────────── */
function Detail({ t }) {
  if (!t) {
    return (
      <div className="detail">
        <div className="empty">
          <div className="big">📩</div>
          <h3 style={{ marginBottom: 8 }}>Pick a ticket</h3>
          <p>Select a service card from the queue to see how the assistant triaged it, what it changed on the booking, and the reply it sent.</p>
        </div>
      </div>
    );
  }
  const d = t.agent_decision || {};
  const conf = Math.round((t.confidence ?? d.confidence ?? 0) * 100);
  const resolved = t.status === "auto_resolved" || t.status === "resolved";

  return (
    <div className="detail" key={t.id}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h2 style={{ fontSize: 22 }}>{t.customer_name}</h2>
        <span className="num mono" style={{ color: "var(--muted)" }}>#{t.number}</span>
        <span className="badge b-channel"><span className="dot" />{t.channel}</span>
        <Badge kind={t.status}>{STATUS_LABEL[t.status]}</Badge>
        {t.urgency === "high" && <Badge kind="high">urgent</Badge>}
      </div>

      <div>
        <div className="block-label">What the customer said</div>
        <div className="quote">“{t.raw_message}”</div>
      </div>

      <div>
        <div className="block-label">How the assistant triaged it</div>
        <div className="decision">
          <div>
            <div className="k">Category</div>
            <div className="val">{CATEGORY_LABEL[t.category] || t.category}</div>
          </div>
          <div>
            <div className="k">Proposed action</div>
            <div className="val" style={{ textTransform: "capitalize" }}>{(d.proposed_action || "none").replace(/_/g, " ")}</div>
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <div className="k">Confidence · {conf}%</div>
            <div className="conf"><span style={{ width: `${conf}%` }} /></div>
          </div>
          {d.reasoning && <div className="reason">{d.reasoning}</div>}
        </div>
      </div>

      <BookingCard t={t} />

      {t.draft_reply && (
        <div>
          <div className="block-label">{resolved ? "Reply sent to customer" : "Drafted reply — awaiting human"}</div>
          <div className="reply">{t.draft_reply}</div>
          <div className="act-row" style={{ marginTop: 12 }}>
            {resolved ? (
              <span className="live"><span className="pulse" /> Sent via {t.channel}</span>
            ) : (
              <>
                <button className="btn primary">Approve &amp; send</button>
                <button className="btn">Edit reply</button>
                <button className="btn">Reassign</button>
              </>
            )}
          </div>
        </div>
      )}

      <Timeline ticketId={t.id} />
    </div>
  );
}

/* ───────────────────────── queue view ───────────────────────── */
function QueueView({ tickets, selectedId, setSelectedId }) {
  const sel = tickets.find((t) => t.id === selectedId);
  return (
    <div className="cols">
      <div className="panel">
        <div className="panel-h">
          <h3>Live queue</h3>
          <span className="pill">{tickets.length} tickets</span>
        </div>
        <div className="queue">
          {tickets.map((t) => (
            <QueueCard key={t.id} t={t} selected={t.id === selectedId} onClick={() => setSelectedId(t.id)} />
          ))}
        </div>
      </div>
      <div className="panel">
        <Detail t={sel} />
      </div>
    </div>
  );
}

/* ───────────────────────── cases view ───────────────────────── */
const OUTCOME_KIND = { refunded: "resolved", replaced: "resolved", resolved: "resolved", disputed: "blocked", pending: "waiting" };
const OUTCOME_LABEL = { refunded: "Refunded", replaced: "Pro replaced", resolved: "Resolved", disputed: "Refund blocked", pending: "Awaiting human" };

function CasesView({ onOpen }) {
  return (
    <div style={{ padding: "0 32px 40px" }}>
      <div className="panel">
        <div className="panel-h"><h3>Cases &amp; disputes</h3><span className="pill">{cases.length} on record</span></div>
        <div className="tablewrap">
          <table className="dtable">
            <thead>
              <tr><th>Ticket</th><th>Customer</th><th>Service</th><th>Professional</th><th>Type</th><th>Amount</th><th>Outcome</th><th>Opened</th></tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.id} className="clickable" onClick={() => onOpen(c.id)}>
                  <td className="mono">#{c.number}</td>
                  <td className="cust">{c.customer}</td>
                  <td style={{ textTransform: "capitalize" }}>{c.service}</td>
                  <td>{c.provider}</td>
                  <td>{c.caseType}</td>
                  <td className="mono">{c.amount != null ? inr(c.amount) : "—"}</td>
                  <td><Badge kind={OUTCOME_KIND[c.outcome] || "neutral"}>{OUTCOME_LABEL[c.outcome] || c.outcome}</Badge></td>
                  <td className="mono" style={{ color: "var(--muted)" }}>{ago(c.openedAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

/* ───────────────────────── providers view ───────────────────────── */
const PROV_KIND = { good: "resolved", watch: "waiting", suspended: "blocked" };
const PROV_LABEL = { good: "Reliable", watch: "On watch", suspended: "Suspended" };

function ReliabilityBar({ noShows }) {
  const pips = 5;
  return (
    <div className="rel-bar">
      {Array.from({ length: pips }).map((_, i) => (
        <span key={i} className={`rel-pip ${i < noShows ? "bad" : i < pips - noShows ? "" : "empty"}`} />
      ))}
      <span className="pill" style={{ marginLeft: 8 }}>{noShows} no-show{noShows === 1 ? "" : "s"}</span>
    </div>
  );
}

function ProvidersView() {
  return (
    <div style={{ padding: "0 32px 40px" }}>
      <div className="panel">
        <div className="panel-h"><h3>Provider reliability</h3><span className="pill">{providers.length} pros</span></div>
        <div className="tablewrap">
          <table className="dtable">
            <thead>
              <tr><th>Professional</th><th>Services</th><th>Area</th><th>Jobs</th><th>Reliability</th><th>Status</th></tr>
            </thead>
            <tbody>
              {providers.map((p) => (
                <tr key={p.name}>
                  <td>
                    <span className="avatar">{initials(p.name)}</span>
                    <span className="cust">{p.name}</span>
                  </td>
                  <td>
                    {p.services.map((s) => (
                      <span key={s} className="chip" style={{ marginRight: 4, textTransform: "capitalize" }}>{s}</span>
                    ))}
                  </td>
                  <td>{p.area}</td>
                  <td className="mono">{p.jobs}</td>
                  <td><ReliabilityBar noShows={p.noShows} /></td>
                  <td><Badge kind={PROV_KIND[p.status]}>{PROV_LABEL[p.status]}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

/* ───────────────────────── messages view ───────────────────────── */
function MessagesView({ tickets, selectedId, setSelectedId }) {
  const withReply = tickets.filter((t) => t.draft_reply);
  const sel = withReply.find((t) => t.id === selectedId) || withReply[0];
  const msgs = sel ? thread(sel) : [];
  return (
    <div className="cols">
      <div className="panel">
        <div className="panel-h"><h3>Conversations</h3><span className="pill">{withReply.length}</span></div>
        <div className="queue">
          {withReply.map((t) => (
            <button key={t.id} className={`scard${(sel && t.id === sel.id) ? " sel" : ""}`} onClick={() => setSelectedId(t.id)}>
              <div className="row1">
                <ServiceIcon service={t.booking?.service} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div className="who">{t.customer_name}</div>
                  <div className="num mono">#{t.number} · {t.channel}</div>
                </div>
                <Badge kind={t.status}>{STATUS_LABEL[t.status]}</Badge>
              </div>
              <div className="msg">{t.raw_message}</div>
            </button>
          ))}
        </div>
      </div>
      <div className="panel">
        {sel ? (
          <>
            <div className="panel-h">
              <h3>{sel.customer_name}</h3>
              <span className="pill">{CATEGORY_LABEL[sel.category] || sel.category}</span>
            </div>
            <div className="thread">
              <div className="msg to-customer">
                <div className="mh">{sel.customer_name}<span className="badge b-channel" style={{ fontSize: 9 }}>{sel.channel}</span></div>
                {sel.raw_message}
              </div>
              {msgs.map((m, i) => (
                <div key={i} className={`msg to-${m.to}`}>
                  <div className="mh">{m.to === "customer" ? "Assistant → " + m.name : "Assistant → " + m.name + " (pro)"}</div>
                  {m.body}
                  <div className="mchan mono">{m.channel}</div>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="detail"><div className="empty"><div className="big">💬</div><p>No conversations yet.</p></div></div>
        )}
      </div>
    </div>
  );
}

/* ───────────────────────── app ───────────────────────── */
const VIEW_META = {
  queue: { h1: "Support queue", p: "Every inbound ticket, triaged and resolved by the assistant the moment it lands." },
  cases: { h1: "Cases & disputes", p: "Refunds, no-shows and the messy ones a human needs to look at." },
  providers: { h1: "Providers", p: "Reliability scored from real no-shows and replacements the assistant made." },
  messages: { h1: "Messages", p: "The two-sided thread — what the assistant told the customer and the pro." },
};

export default function App() {
  const [view, setView] = useState("queue");
  const firstResolved = useMemo(
    () => allTickets.find((t) => t.booking && t.booking.last_action) || allTickets[0],
    []
  );
  const [selectedId, setSelectedId] = useState(firstResolved?.id);

  const counts = {
    queue: allTickets.length,
    cases: cases.length,
    providers: providers.length,
    messages: allTickets.filter((t) => t.draft_reply).length,
  };
  const meta = VIEW_META[view];

  return (
    <div className="shell">
      <Sidebar view={view} setView={setView} counts={counts} />
      <main className="main">
        <header className="topbar">
          <div className="title">
            <h1>{meta.h1}</h1>
            <p>{meta.p}</p>
          </div>
          <div className="spacer" />
          <div className="live"><span className="pulse" /> Live · {fmtDateTime("2026-06-24T17:10:00Z")} IST</div>
        </header>

        {view === "queue" && <Stats />}

        {view === "queue" && (
          <QueueView tickets={allTickets} selectedId={selectedId} setSelectedId={setSelectedId} />
        )}
        {view === "cases" && (
          <CasesView onOpen={(id) => { setSelectedId(id); setView("queue"); }} />
        )}
        {view === "providers" && <ProvidersView />}
        {view === "messages" && (
          <MessagesView tickets={allTickets} selectedId={selectedId} setSelectedId={setSelectedId} />
        )}
      </main>
    </div>
  );
}
