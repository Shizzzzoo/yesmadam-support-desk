#input_type_name: CommitEnRouteInput
#output_type_name: CommitEnRouteResult
#function_name: commit_en_route

from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


class CommitEnRouteInput(BaseModel):
    response_id: str


class CommitEnRouteResult(BaseModel):
    ticket_id: str
    detail: str


def build_customer_reply(pro_name: str, eta_minutes: int, on_site: bool) -> str:
    who = pro_name or "your professional"
    if on_site:
        return (f"Good news — {who} reports they're already on site for your appointment. "
                f"If that's not what you're seeing, reply and we'll jump in.")
    return (f"Good news — {who} is on the way and should reach you in about "
            f"{eta_minutes} minutes. Thanks for your patience!")


async def commit_en_route(ctx: FunctionContext, data: CommitEnRouteInput) -> CommitEnRouteResult:
    pod = Pod.from_env()
    resp = pod.table("provider_responses").get(data.response_id)
    ticket_id = resp["ticket_id"]
    booking_id = resp.get("booking_id") or ""
    on_site = (resp.get("status") == "on_site")
    eta = int(resp.get("eta_minutes") or 0)
    pro = resp.get("professional_name", "")

    if booking_id:
        pod.table("bookings").update(booking_id, {
            "provider_state": "en_route",
            "last_action": ("Pro reports on-site" if on_site else f"Pro en route, ETA {eta}m"),
        })

    reply = build_customer_reply(pro, eta, on_site)
    ticket_status = "waiting_approval" if on_site else "auto_resolved"
    pod.table("tickets").update(ticket_id, {"status": ticket_status, "draft_reply": reply})
    pod.records.bulk_create("ticket_events", [{
        "ticket_id": ticket_id, "kind": "action_taken", "actor": "agent",
        "note": ("On-site claim — parked for human + proof-of-service" if on_site
                 else f"Pro en route, ETA {eta}m; customer reassured"),
    }])
    if not on_site:
        pod.functions.execute("notify_customer", {"ticket_id": ticket_id})
    return CommitEnRouteResult(ticket_id=ticket_id, detail=("on_site->human" if on_site else "en_route"))
