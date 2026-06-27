import tickets from "./tickets.json";
import bookings from "./bookings.json";
import events from "./ticket_events.json";
import professionals from "./professionals.json";
import evidence from "./service_evidence.json";
import providerResponses from "./provider_responses.json";

export const SERVICE_ICON = {
  haircut: "✂️", facial: "🧖", massage: "💆", manicure: "💅", waxing: "🪒",
};

const bookingById = Object.fromEntries(bookings.map((b) => [b.id, b]));

export const CATEGORY_LABEL = {
  reschedule: "Reschedule", cancel_refund: "Cancel & refund", no_show: "No-show",
  where_is_pro: "Where's my pro", other: "Other", ambiguous: "Needs a human",
};

// ── Tickets, newest first, joined to their booking ──
export const allTickets = [...tickets]
  .sort((a, b) => (b.number || 0) - (a.number || 0))
  .map((t) => ({ ...t, booking: t.booking_id ? bookingById[t.booking_id] : null }));

export function eventsFor(ticketId) {
  return events
    .filter((e) => e.ticket_id === ticketId)
    .sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
}

export function evidenceFor(bookingId) {
  return evidence.filter((e) => e.booking_id === bookingId);
}

// ── Provider coordination (the new loop) ──
// Latest coordination row for a ticket: the desk alerted the assigned pro and is
// waiting on / has received their reply (late / reschedule / can't make it / on-site),
// or the 5-minute SLA expired (no_response).
export function coordinationFor(ticketId) {
  const rows = providerResponses
    .filter((r) => r.ticket_id === ticketId)
    .sort((a, b) => new Date(b.alerted_at) - new Date(a.alerted_at));
  return rows[0] || null;
}
export const PROVIDER_STATUS_LABEL = {
  awaiting: "Awaiting reply",
  late: "Running late",
  reschedule: "Proposed reschedule",
  on_site: "Reports on-site",
  cant_make_it: "Can't make it",
  no_response: "No reply (timed out)",
  customer_accepted: "Customer accepted",
  customer_declined: "Customer declined",
};
export const SLA_MINUTES = 5;

// ── Headline metrics ──
function rate() {
  const considered = allTickets.filter((t) => t.status !== "new");
  const auto = considered.filter((t) => t.status === "auto_resolved").length;
  return considered.length ? Math.round((auto / considered.length) * 100) : 0;
}
export const metrics = {
  total: allTickets.length,
  autoResolved: allTickets.filter((t) => t.status === "auto_resolved").length,
  needsHuman: allTickets.filter((t) => ["triaged", "escalated", "waiting_approval"].includes(t.status)).length,
  rate: rate(),
  bookingsActed: bookings.filter((b) => b.last_action).length,
  refundsBlocked: bookings.filter((b) => b.refund_status === "blocked" || b.refund_status === "denied").length,
  // a refund is "protected" when a service-proven booking still has money on it, unrefunded
  protected: bookings.filter(
    (b) => (b.start_otp_verified || b.check_in_at || b.status === "in_progress") && b.refund_status !== "full"
  ).length,
  prosCoordinated: providerResponses.length,
  awaitingProvider: providerResponses.filter((r) => r.status === "awaiting").length,
  enRouteLocks: bookings.filter((b) => ["alerted", "en_route"].includes(b.provider_state)).length,
};

// ── Cases: problematic treatments (the separate history store) ──
export const cases = allTickets
  .filter((t) => ["cancel_refund", "no_show"].includes(t.category) || ["escalated", "triaged", "waiting_approval"].includes(t.status))
  .map((t) => {
    const b = t.booking;
    const proven = b && (b.start_otp_verified || b.check_in_at || b.status === "in_progress");
    let outcome = "pending";
    if (t.status === "auto_resolved" || t.status === "resolved") {
      if (b?.refund_status === "full") outcome = "refunded";
      else if (b?.status === "scheduled" && b?.previous_professional) outcome = "replaced";
      else outcome = "resolved";
    } else if (proven && t.category === "cancel_refund") outcome = "disputed";
    return {
      id: t.id,
      number: t.number,
      customer: t.customer_name,
      provider: b?.professional_name || "—",
      service: b?.service || "—",
      caseType: t.category === "no_show" ? "No-show" : t.category === "cancel_refund" ? (proven ? "Dispute" : "Cancellation") : "Escalation",
      outcome,
      amount: b?.amount,
      openedAt: t.created_at,
    };
  });

// ── Provider reliability (derived) ──
// Count a no-show against the pro who was REPLACED, never the replacement.
// Authoritative phrasings: "(was <Pro>, no-show)" in booking.last_action and
// "replace no-show <Pro>" in an action_taken event note.
const noShowCounts = (() => {
  const counts = {};
  // Resolve one no-show pro per replacement incident (booking), so each counts once.
  bookings.forEach((b) => {
    let pro = (b.last_action || "").match(/\(was (.+?),\s*no-show\)/i)?.[1];
    if (!pro) {
      // fall back to the action_taken event for this booking
      const ev = events.find(
        (e) => e.kind === "action_taken" && new RegExp(`booking #${b.code}\\b`).test(e.note || "")
      );
      pro = (ev?.note || "").match(/replace\s+no-show\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/)?.[1];
    }
    if (pro) counts[pro.trim()] = (counts[pro.trim()] || 0) + 1;
  });
  return counts;
})();

export const providers = professionals.map((p) => {
  const theirBookings = bookings.filter((b) => b.professional_name === p.name);
  const noShows = noShowCounts[p.name] || 0;
  const status = noShows >= 3 ? "suspended" : noShows >= 2 ? "watch" : "good";
  return {
    name: p.name,
    services: p.services || [],
    area: p.area,
    active: p.active !== false,
    jobs: theirBookings.length,
    noShows,
    status,
  };
}).sort((a, b) => b.noShows - a.noShows || b.jobs - a.jobs);

// ── Two-sided message thread for a ticket (customer reply is real; provider coordination derived) ──
export function thread(t) {
  const out = [];
  const b = t.booking;
  if (t.draft_reply) {
    out.push({ to: "customer", name: t.customer_name, channel: t.channel, body: t.draft_reply });
  }
  if (b) {
    const action = t.agent_decision?.proposed_action;
    if (action === "reschedule") {
      out.push({ to: "provider", name: b.professional_name, channel: "whatsapp",
        body: `Heads up — booking #${b.code} (${b.service}) for ${t.customer_name} was moved. Please check your updated schedule.` });
    } else if (action === "refund" || t.category === "cancel_refund") {
      out.push({ to: "provider", name: b.professional_name, channel: "whatsapp",
        body: `Booking #${b.code} (${b.service}) for ${t.customer_name} was cancelled. No action needed from your side.` });
    } else if (action === "assign_replacement" || t.category === "no_show") {
      if (b.previous_professional) {
        out.push({ to: "provider", name: b.previous_professional, channel: "whatsapp",
          body: `You were marked as a no-show for booking #${b.code}. This affects your reliability score — please reach out to ops.` });
      }
      out.push({ to: "provider", name: b.professional_name, channel: "whatsapp",
        body: `New job assigned: booking #${b.code} (${b.service}) for ${t.customer_name} at ${b.address}. Please head over.` });
    }
  }
  return out;
}

export const currentUser = "demo@yesmadam.example";
