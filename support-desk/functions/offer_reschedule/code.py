#input_type_name: OfferRescheduleInput
#output_type_name: OfferRescheduleResult
#function_name: offer_reschedule

from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


class OfferRescheduleInput(BaseModel):
    response_id: str


class OfferRescheduleResult(BaseModel):
    ticket_id: str
    detail: str


def build_offer_reply(pro_name: str, new_time: str) -> str:
    who = pro_name or "Your professional"
    return (f"{who} can't make the original slot but offers to come at {new_time} instead. "
            f"Reply YES to confirm, or NO and we'll cancel and refund you.")


async def offer_reschedule(ctx: FunctionContext, data: OfferRescheduleInput) -> OfferRescheduleResult:
    pod = Pod.from_env()
    resp = pod.table("provider_responses").get(data.response_id)
    ticket_id = resp["ticket_id"]
    booking_id = resp.get("booking_id") or ""
    new_time = str(resp.get("proposed_new_time") or "")
    pro = resp.get("professional_name", "")

    if booking_id:
        pod.table("bookings").update(booking_id, {
            "provider_state": "en_route",
            "last_action": f"Reschedule offered to {new_time} (awaiting customer)",
        })
    reply = build_offer_reply(pro, new_time)
    pod.table("tickets").update(ticket_id, {"status": "awaiting_provider", "draft_reply": reply})
    pod.functions.execute("notify_customer", {"ticket_id": ticket_id})
    pod.records.bulk_create("ticket_events", [{
        "ticket_id": ticket_id, "kind": "action_taken", "actor": "agent",
        "note": f"Reschedule offer sent: {new_time}",
    }])
    return OfferRescheduleResult(ticket_id=ticket_id, detail=f"offered {new_time}")
