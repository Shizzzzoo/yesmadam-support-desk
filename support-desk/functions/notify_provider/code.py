#input_type_name: NotifyProviderInput
#output_type_name: NotifyProviderResult
#function_name: notify_provider

from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod

# Gmail (native LEMMA provider) send-email operation. If the exact id/payload differ
# in your org, confirm with: lemma connectors operations search workspace-gmail "send email"
AUTH_CONFIG = "workspace-gmail"
SEND_OP = "gmail_send_email"


class NotifyProviderInput(BaseModel):
    response_id: str


class NotifyProviderResult(BaseModel):
    sent: bool
    detail: str


def build_alert_body(customer_name: str, service: str, address: str,
                     scheduled: str, sla_minutes: int) -> str:
    return (
        f"Hi — a YesMadam client is waiting on you.\n\n"
        f"Client: {customer_name}\nService: {service}\n"
        f"Where: {address}\nWhen: {scheduled}\n\n"
        f"Please reply within {sla_minutes} minutes with one of:\n"
        f"  1) RUNNING LATE — I'll be there in N minutes\n"
        f"  2) RESCHEDULE — propose a new time\n"
        f"  3) CAN'T MAKE IT today\n"
        f"  4) I'M ON SITE already\n\n"
        f"If we don't hear back in {sla_minutes} minutes we'll resolve it for the client automatically.\n"
        f"— YesMadam Ops"
    )


async def notify_provider(ctx: FunctionContext, data: NotifyProviderInput) -> NotifyProviderResult:
    pod = Pod.from_env()
    resp = pod.table("provider_responses").get(data.response_id)
    booking = pod.table("bookings").get(resp["booking_id"]) if resp.get("booking_id") else {}

    pros = pod.records.list("professionals", limit=200).to_dict()["items"]
    pro = next((p for p in pros if (p.get("name") or "").strip().lower()
                == (resp.get("professional_name") or "").strip().lower()), None)
    to_email = (pro or {}).get("contact_email")

    if not to_email:
        pod.records.bulk_create("ticket_events", [{
            "ticket_id": resp["ticket_id"], "kind": "action_taken", "actor": "agent",
            "note": f"Provider alert skipped — no contact_email for {resp.get('professional_name')}"[:1900],
        }])
        return NotifyProviderResult(sent=False, detail="No provider contact email — SLA will resolve.")

    body = build_alert_body(
        customer_name=booking.get("customer_name", "your client"),
        service=booking.get("service", "service"),
        address=booking.get("address", ""),
        scheduled=str(booking.get("scheduled_at", "")),
        sla_minutes=5,
    )
    try:
        pod.connectors.execute(AUTH_CONFIG, SEND_OP, {
            "recipient_email": to_email,
            "subject": f"⏳ Client waiting — booking #{booking.get('code', '')}",
            "body": body,
        })
    except Exception as exc:  # never break the resolution over a notification
        pod.records.bulk_create("ticket_events", [{
            "ticket_id": resp["ticket_id"], "kind": "action_taken", "actor": "agent",
            "note": f"Provider alert email failed: {exc}"[:1900],
        }])
        return NotifyProviderResult(sent=False, detail=f"Send failed: {exc}")

    pod.records.bulk_create("ticket_events", [{
        "ticket_id": resp["ticket_id"], "kind": "action_taken", "actor": "agent",
        "note": f"Alerted {resp.get('professional_name')} ({to_email}): client waiting",
    }])
    return NotifyProviderResult(sent=True, detail=f"Alerted {to_email}")
