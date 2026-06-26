#input_type_name: NotifyCustomerInput
#output_type_name: NotifyCustomerResult
#function_name: notify_customer

# Notifications are recorded in-pod (ticket_events) — reliable, no external account.
# The delivery channel is pluggable: swap this for an API-key connector (Resend email
# / Twilio SMS) when you want real outbound; the workflow doesn't change.
from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


class NotifyCustomerInput(BaseModel):
    ticket_id: str


class NotifyCustomerResult(BaseModel):
    sent: bool
    detail: str


async def notify_customer(ctx: FunctionContext, data: NotifyCustomerInput) -> NotifyCustomerResult:
    pod = Pod.from_env()

    ticket = pod.table("tickets").get(data.ticket_id)
    reply = ticket.get("draft_reply") or "Your YesMadam booking has been updated by our support team."
    booking_id = ticket.get("booking_id")
    code = None
    if booking_id:
        try:
            code = pod.table("bookings").get(booking_id).get("code")
        except Exception:
            pass

    pod.records.bulk_create("ticket_events", [{
        "ticket_id": data.ticket_id, "kind": "resolved", "actor": "agent",
        "note": (f"Customer notified" + (f" (booking #{code})" if code else "") + f": {reply}")[:1900],
    }])
    return NotifyCustomerResult(sent=True, detail="Customer notified in-app (delivery channel pluggable).")
