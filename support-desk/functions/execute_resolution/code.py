#input_type_name: ExecuteResolutionInput
#output_type_name: ExecuteResolutionResult
#function_name: execute_resolution

from typing import Optional
from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


class ExecuteResolutionInput(BaseModel):
    ticket_id: str
    action: str = "none"            # reschedule | refund | assign_replacement | none
    booking_id: str = ""
    proposed_new_time: str = ""     # ISO datetime, for reschedule
    reply: str = ""
    resolution_status: str          # auto_resolved | resolved | escalated
    actor: str = "agent"            # agent | human


class ExecuteResolutionResult(BaseModel):
    ticket_id: str
    ticket_status: str
    booking_changed: bool
    booking_summary: str


def _norm(s) -> str:
    return (s or "").strip().lower()


def _pick_replacement(pod: Pod, booking: dict) -> Optional[dict]:
    """Find an active professional offering the booking's service in the same area —
    never the professional who no-showed (case/space-insensitive exclusion)."""
    pros = pod.records.list("professionals", limit=100).to_dict()["items"]
    service = booking.get("service")
    area = _norm(booking.get("address"))
    current = _norm(booking.get("professional_name"))
    candidates = [
        p for p in pros
        if p.get("active", True)
        and _norm(p.get("name")) != current        # never re-assign the no-show pro
        and service in (p.get("services") or [])
    ]
    # Prefer a candidate serving the customer's locality; otherwise any candidate.
    for p in candidates:
        if p.get("area") and _norm(p.get("area")) in area:
            return p
    return candidates[0] if candidates else None


async def execute_resolution(ctx: FunctionContext, data: ExecuteResolutionInput) -> ExecuteResolutionResult:
    pod = Pod.from_env()
    bookings = pod.table("bookings")

    booking_changed = False
    booking_summary = "no booking change"
    events = []

    # --- 1. Take the real action against the booking ----------------------------
    if data.action != "none" and data.booking_id:
        booking = bookings.get(data.booking_id)

        if data.action == "reschedule" and data.proposed_new_time:
            bookings.update(data.booking_id, {
                "status": "rescheduled",
                "scheduled_at": data.proposed_new_time,
                "last_action": f"Rescheduled to {data.proposed_new_time} by {data.actor}",
            })
            booking_changed = True
            booking_summary = f"booking #{booking.get('code')} rescheduled to {data.proposed_new_time}"

        elif data.action == "refund":
            amt = booking.get("amount")
            prepaid = booking.get("payment_status", "prepaid") == "prepaid"
            update = {"status": "cancelled"}
            if prepaid:
                update["refund_status"] = "full"
                update["last_action"] = f"Cancelled + full refund (₹{amt}) by {data.actor}"
                booking_summary = f"booking #{booking.get('code')} cancelled, ₹{amt} refunded (prepaid)"
            else:
                update["refund_status"] = "none"
                update["last_action"] = f"Cancelled (pay-after — no money was taken) by {data.actor}"
                booking_summary = f"booking #{booking.get('code')} cancelled, no payment to refund"
            bookings.update(data.booking_id, update)
            booking_changed = True

        elif data.action == "assign_replacement":
            original_pro = booking.get("professional_name") or "the original professional"
            replacement = _pick_replacement(pod, booking)
            # Guard: only accept a genuinely DIFFERENT professional.
            if replacement and _norm(replacement.get("name")) != _norm(original_pro):
                bookings.update(data.booking_id, {
                    "professional_name": replacement["name"],
                    "status": "scheduled",
                    "last_action": f"Replacement {replacement['name']} assigned (was {original_pro}, no-show) by {data.actor}",
                })
                booking_changed = True
                booking_summary = f"booking #{booking.get('code')}: {replacement['name']} assigned to replace no-show {original_pro}"
            else:
                # No DIFFERENT replacement available → fall back to full refund (policy).
                bookings.update(data.booking_id, {
                    "status": "cancelled",
                    "refund_status": "full",
                    "last_action": f"No replacement available for {original_pro}'s no-show → full refund (₹{booking.get('amount')}) by {data.actor}",
                })
                booking_changed = True
                booking_summary = f"booking #{booking.get('code')}: no replacement, ₹{booking.get('amount')} refunded"

        if booking_changed:
            events.append({
                "ticket_id": data.ticket_id,
                "kind": "action_taken",
                "actor": data.actor,
                "note": booking_summary,
            })

    # --- 2. Resolve the ticket --------------------------------------------------
    ticket_update = {"status": data.resolution_status}
    if data.reply:
        ticket_update["draft_reply"] = data.reply
    pod.table("tickets").update(data.ticket_id, ticket_update)

    if data.resolution_status == "escalated":
        events.append({"ticket_id": data.ticket_id, "kind": "escalated", "actor": data.actor,
                       "note": "Routed to human review (gate not satisfied)."})
    else:
        if data.actor == "human":
            events.append({"ticket_id": data.ticket_id, "kind": "approved", "actor": "human",
                           "note": "Human approved the resolution."})
        events.append({"ticket_id": data.ticket_id, "kind": "resolved", "actor": data.actor,
                       "note": f"Ticket {data.resolution_status}. {booking_summary}"})

    if events:
        pod.records.bulk_create("ticket_events", events)

    return ExecuteResolutionResult(
        ticket_id=data.ticket_id,
        ticket_status=data.resolution_status,
        booking_changed=booking_changed,
        booking_summary=booking_summary,
    )
