#input_type_name: NotifyProviderInput
#output_type_name: NotifyProviderResult
#function_name: notify_provider

# The "client is waiting" alert is recorded in-pod (ticket_events) — reliable, no
# external account. The delivery channel is pluggable: swap this for an API-key
# connector (Twilio SMS / Resend email) for real outbound; the workflow doesn't change.
from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


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

    body = build_alert_body(
        customer_name=booking.get("customer_name", "your client"),
        service=booking.get("service", "service"),
        address=booking.get("address", ""),
        scheduled=str(booking.get("scheduled_at", "")),
        sla_minutes=5,
    )
    pod.records.bulk_create("ticket_events", [{
        "ticket_id": resp["ticket_id"], "kind": "action_taken", "actor": "agent",
        "note": (f"Provider {resp.get('professional_name')} alerted (client waiting): {body}")[:1900],
    }])
    return NotifyProviderResult(sent=True, detail=f"Alerted {resp.get('professional_name')} in-app.")
