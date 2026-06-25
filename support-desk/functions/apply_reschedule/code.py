#input_type_name: ApplyRescheduleInput
#output_type_name: ApplyRescheduleResult
#function_name: apply_reschedule

from datetime import datetime, timezone
from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


class ApplyRescheduleInput(BaseModel):
    response_id: str


class ApplyRescheduleResult(BaseModel):
    ticket_id: str
    detail: str


def is_valid_future(new_time_iso: str, now_iso: str) -> bool:
    try:
        nt = datetime.fromisoformat(new_time_iso.replace("Z", "+00:00"))
        now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        return nt > now
    except Exception:
        return False


async def apply_reschedule(ctx: FunctionContext, data: ApplyRescheduleInput) -> ApplyRescheduleResult:
    pod = Pod.from_env()
    resp = pod.table("provider_responses").get(data.response_id)
    ticket_id = resp["ticket_id"]
    booking_id = resp.get("booking_id") or ""
    new_time = str(resp.get("proposed_new_time") or "")
    now = datetime.now(timezone.utc).isoformat()

    if not booking_id or not is_valid_future(new_time, now):
        pod.functions.execute("stand_down", {"response_id": data.response_id})
        return ApplyRescheduleResult(ticket_id=ticket_id, detail="invalid new_time -> stand_down")

    pod.table("bookings").update(booking_id, {"provider_state": "en_route"})
    pod.functions.execute("execute_resolution", {
        "ticket_id": ticket_id,
        "action": "reschedule",
        "booking_id": booking_id,
        "proposed_new_time": new_time,
        "reply": f"Confirmed — your appointment is now at {new_time}. See you then!",
        "resolution_status": "auto_resolved",
        "actor": "agent",
    })
    return ApplyRescheduleResult(ticket_id=ticket_id, detail=f"rescheduled to {new_time}")
