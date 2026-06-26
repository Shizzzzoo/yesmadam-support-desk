#input_type_name: FileTicketInput
#output_type_name: FileTicketResult
#function_name: file_ticket

from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


class FileTicketInput(BaseModel):
    customer_name: str
    message: str
    booking_id: str = ""
    channel: str = "app_chat"   # one of: whatsapp | app_chat | email


class FileTicketResult(BaseModel):
    ticket_id: str
    detail: str


def build_ticket_payload(customer_name: str, message: str, booking_id: str = "", channel: str = "app_chat") -> dict:
    payload = {
        "customer_name": customer_name,
        "raw_message": message,
        "channel": channel or "app_chat",
        "status": "new",
    }
    if booking_id:
        payload["booking_id"] = booking_id
    return payload


async def file_ticket(ctx: FunctionContext, data: FileTicketInput) -> FileTicketResult:
    pod = Pod.from_env()
    payload = build_ticket_payload(data.customer_name, data.message, data.booking_id, data.channel)
    created = pod.records.create("tickets", payload)   # INSERT fires new-ticket -> handle_ticket
    return FileTicketResult(ticket_id=created["id"], detail=f"Filed ticket for {data.customer_name}")
