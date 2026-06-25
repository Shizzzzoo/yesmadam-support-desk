#input_type_name: SweepProviderSlaInput
#output_type_name: SweepProviderSlaResult
#function_name: sweep_provider_sla

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod

SLA_MINUTES = 5


class SweepProviderSlaInput(BaseModel):
    pass


class SweepProviderSlaResult(BaseModel):
    swept: int
    detail: str


def next_status(status: str, minutes_elapsed: float, sla: int) -> Optional[str]:
    if minutes_elapsed < sla:
        return None
    if status == "awaiting":
        return "no_response"
    if status == "reschedule":
        return "customer_declined"
    return None


def _elapsed_minutes(alerted_at: str, now: datetime) -> float:
    try:
        t = datetime.fromisoformat((alerted_at or "").replace("Z", "+00:00"))
        return (now - t).total_seconds() / 60.0
    except Exception:
        return 0.0


async def sweep_provider_sla(ctx: FunctionContext, data: SweepProviderSlaInput) -> SweepProviderSlaResult:
    pod = Pod.from_env()
    now = datetime.now(timezone.utc)
    rows = pod.records.list("provider_responses", limit=500).to_dict()["items"]
    swept = 0
    for r in rows:
        nxt = next_status(r.get("status") or "", _elapsed_minutes(r.get("alerted_at"), now), SLA_MINUTES)
        if nxt:
            pod.table("provider_responses").update(r["id"], {
                "status": nxt, "responded_at": now.isoformat(),
                "note": ((r.get("note") or "") + f" | SLA expiry -> {nxt}")[:1900],
            })
            swept += 1
    return SweepProviderSlaResult(swept=swept, detail=f"expired {swept} row(s)")
