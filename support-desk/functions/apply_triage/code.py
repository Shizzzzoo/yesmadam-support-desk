#input_type_name: ApplyTriageInput
#output_type_name: ApplyTriageResult
#function_name: apply_triage

from typing import Optional
from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


class ApplyTriageInput(BaseModel):
    ticket_id: str
    category: str
    urgency: str = "normal"
    confidence: float = 0.0
    booking_id: str = ""           # "" when the agent found no matching booking
    proposed_action: str = "none"  # reschedule | refund | assign_replacement | none
    draft_reply: str = ""
    reasoning: str = ""


class ApplyTriageResult(BaseModel):
    ticket_id: str
    status: str


async def apply_triage(ctx: FunctionContext, data: ApplyTriageInput) -> ApplyTriageResult:
    pod = Pod.from_env()

    update = {
        "category": data.category,
        "urgency": data.urgency,
        "confidence": data.confidence,
        "draft_reply": data.draft_reply,
        "status": "triaged",
        "agent_decision": {
            "category": data.category,
            "urgency": data.urgency,
            "confidence": data.confidence,
            "proposed_action": data.proposed_action,
            "booking_id": data.booking_id,
            "reasoning": data.reasoning,
        },
    }
    # Only set the FK when a booking was actually matched (empty string is not a valid UUID).
    if data.booking_id:
        update["booking_id"] = data.booking_id

    pod.table("tickets").update(data.ticket_id, update)

    pod.records.bulk_create("ticket_events", [
        {
            "ticket_id": data.ticket_id,
            "kind": "classified",
            "actor": "agent",
            "note": f"{data.category} (confidence {round(data.confidence, 2)}) → proposed {data.proposed_action}. {data.reasoning}"[:1900],
        }
    ])

    return ApplyTriageResult(ticket_id=data.ticket_id, status="triaged")
