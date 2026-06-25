#input_type_name: AlertProviderInput
#output_type_name: AlertProviderResult
#function_name: alert_provider

from datetime import datetime, timezone
from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod

SLA_MINUTES = 5


class AlertProviderInput(BaseModel):
    ticket_id: str
    booking_id: str = ""


class AlertProviderResult(BaseModel):
    ticket_id: str
    response_id: str
    alerted: bool
    detail: str


def build_holding_reply(pro_name: str, sla_minutes: int) -> str:
    return (
        f"Thanks for letting us know. We've messaged your professional"
        f"{(' ' + pro_name) if pro_name else ''} from YesMadam's side and asked them to "
        f"confirm. Please hold ~{sla_minutes} minutes. If we don't hear back, we'll "
        f"refund you automatically — you won't need to chase this."
    )


def should_alert(provider_state: str) -> bool:
    return (provider_state or "idle") not in ("alerted", "en_route")


async def alert_provider(ctx: FunctionContext, data: AlertProviderInput) -> AlertProviderResult:
    pod = Pod.from_env()
    bookings = pod.table("bookings")
    booking = bookings.get(data.booking_id) if data.booking_id else {}
    pro_name = booking.get("professional_name", "") if booking else ""
    state = (booking.get("provider_state") or "idle") if booking else "idle"

    now = datetime.now(timezone.utc).isoformat()

    if booking and not should_alert(state):
        pod.table("tickets").update(data.ticket_id, {
            "status": "triaged",  # parked awaiting the provider; provider_responses + booking.provider_state carry the coordination state (tickets.status enum can't be extended on a live table)
            "draft_reply": build_holding_reply(pro_name, SLA_MINUTES),
        })
        pod.records.bulk_create("ticket_events", [{
            "ticket_id": data.ticket_id, "kind": "action_taken", "actor": "agent",
            "note": f"Linked to existing provider coordination (state={state}); no second alert.",
        }])
        return AlertProviderResult(ticket_id=data.ticket_id, response_id="",
                                   alerted=False, detail="linked to open coordination")

    created = pod.records.create("provider_responses", {
        "ticket_id": data.ticket_id,
        "booking_id": data.booking_id,
        "professional_name": pro_name,
        "status": "awaiting",
        "alerted_at": now,
    })
    response_id = created["id"]

    if data.booking_id:
        bookings.update(data.booking_id, {"provider_state": "alerted"})

    pod.table("tickets").update(data.ticket_id, {
        "status": "awaiting_provider",
        "draft_reply": build_holding_reply(pro_name, SLA_MINUTES),
    })

    try:
        pod.functions.execute("notify_provider", {"response_id": response_id})
    except Exception as exc:
        pod.records.bulk_create("ticket_events", [{
            "ticket_id": data.ticket_id, "kind": "action_taken", "actor": "agent",
            "note": f"notify_provider call failed (SLA will still resolve): {exc}"[:1900],
        }])

    return AlertProviderResult(ticket_id=data.ticket_id, response_id=response_id,
                               alerted=True, detail=f"alerted {pro_name or 'provider'}")
