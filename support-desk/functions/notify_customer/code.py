#input_type_name: NotifyCustomerInput
#output_type_name: NotifyCustomerResult
#function_name: notify_customer

from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod

# Gmail (native LEMMA provider) send-email operation. If the exact id/payload differ
# in your org, confirm with: lemma connectors operations search workspace-gmail "send email"
AUTH_CONFIG = "workspace-gmail"
SEND_OP = "gmail_send_email"


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

    to_email = None
    code = None
    if booking_id:
        booking = pod.table("bookings").get(booking_id)
        to_email = booking.get("customer_email")
        code = booking.get("code")

    if not to_email:
        return NotifyCustomerResult(sent=False, detail="No customer email on file — skipped.")

    subject = f"Update on your YesMadam booking" + (f" #{code}" if code else "")
    body = reply + "\n\n— YesMadam Support"

    try:
        pod.connectors.execute(
            AUTH_CONFIG, SEND_OP,
            {"recipient_email": to_email, "subject": subject, "body": body},
        )
    except Exception as exc:  # never break the resolution over a notification
        pod.records.bulk_create("ticket_events", [{
            "ticket_id": data.ticket_id, "kind": "resolved", "actor": "agent",
            "note": f"Email notification failed: {exc}"[:1900],
        }])
        return NotifyCustomerResult(sent=False, detail=f"Send failed: {exc}")

    pod.records.bulk_create("ticket_events", [{
        "ticket_id": data.ticket_id, "kind": "resolved", "actor": "agent",
        "note": f"Confirmation email sent to {to_email}",
    }])
    return NotifyCustomerResult(sent=True, detail=f"Emailed {to_email}")
