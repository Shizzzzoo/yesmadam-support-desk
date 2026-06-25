#input_type_name: ProviderStandNoticeInput
#output_type_name: ProviderStandNoticeResult
#function_name: provider_stand_notice

from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


class ProviderStandNoticeInput(BaseModel):
    response_id: str


class ProviderStandNoticeResult(BaseModel):
    detail: str


async def provider_stand_notice(ctx: FunctionContext, data: ProviderStandNoticeInput) -> ProviderStandNoticeResult:
    pod = Pod.from_env()
    resp = pod.table("provider_responses").get(data.response_id)
    pod.records.bulk_create("ticket_events", [{
        "ticket_id": resp["ticket_id"], "kind": "action_taken", "actor": "agent",
        "note": f"Late provider reply ignored — booking already resolved (status={resp.get('status')}).",
    }])
    return ProviderStandNoticeResult(detail="late reply ignored")
