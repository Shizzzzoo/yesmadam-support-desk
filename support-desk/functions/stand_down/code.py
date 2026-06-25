#input_type_name: StandDownInput
#output_type_name: StandDownResult
#function_name: stand_down

from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


class StandDownInput(BaseModel):
    response_id: str


class StandDownResult(BaseModel):
    ticket_id: str
    detail: str


def resolution_for(status: str) -> str:
    # One proven path: assign a replacement when possible; execute_resolution falls
    # back to a full refund when no active same-service pro is available.
    return "assign_replacement"


async def stand_down(ctx: FunctionContext, data: StandDownInput) -> StandDownResult:
    pod = Pod.from_env()
    resp = pod.table("provider_responses").get(data.response_id)
    ticket_id = resp["ticket_id"]
    booking_id = resp.get("booking_id") or ""

    if booking_id:
        pod.table("bookings").update(booking_id, {"provider_state": "stood_down"})

    action = resolution_for(resp.get("status") or "no_response")
    pod.functions.execute("execute_resolution", {
        "ticket_id": ticket_id,
        "action": action,
        "booking_id": booking_id,
        "reply": "We couldn't confirm your professional in time, so we've sorted this out for you — details below.",
        "resolution_status": "auto_resolved",
        "actor": "agent",
    })
    pod.records.bulk_create("ticket_events", [{
        "ticket_id": ticket_id, "kind": "action_taken", "actor": "agent",
        "note": f"Stood down (status={resp.get('status')}) -> {action} (refund fallback if no pro).",
    }])
    return StandDownResult(ticket_id=ticket_id, detail=f"stood down -> {action}")
