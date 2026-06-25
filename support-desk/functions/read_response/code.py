#input_type_name: ReadResponseInput
#output_type_name: ReadResponseResult
#function_name: read_response

from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


class ReadResponseInput(BaseModel):
    response_id: str


class ReadResponseResult(BaseModel):
    response_id: str
    status: str = ""
    ticket_id: str = ""
    booking_id: str = ""
    professional_name: str = ""
    eta_minutes: int = 0
    proposed_new_time: str = ""
    provider_state: str = "idle"
    booking_status: str = ""


async def read_response(ctx: FunctionContext, data: ReadResponseInput) -> ReadResponseResult:
    pod = Pod.from_env()
    r = pod.table("provider_responses").get(data.response_id)
    booking_id = r.get("booking_id") or ""
    provider_state, booking_status = "idle", ""
    if booking_id:
        b = pod.table("bookings").get(booking_id)
        provider_state = b.get("provider_state") or "idle"
        booking_status = b.get("status") or ""
    return ReadResponseResult(
        response_id=data.response_id,
        status=r.get("status") or "",
        ticket_id=r.get("ticket_id") or "",
        booking_id=booking_id,
        professional_name=r.get("professional_name") or "",
        eta_minutes=int(r.get("eta_minutes") or 0),
        proposed_new_time=str(r.get("proposed_new_time") or ""),
        provider_state=provider_state,
        booking_status=booking_status,
    )
