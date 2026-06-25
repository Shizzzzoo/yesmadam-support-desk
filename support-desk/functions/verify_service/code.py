#input_type_name: VerifyServiceInput
#output_type_name: VerifyServiceResult
#function_name: verify_service

from pydantic import BaseModel
from lemma_sdk import FunctionContext, Pod


class VerifyServiceInput(BaseModel):
    booking_id: str = ""   # "" when triage found no booking — then nothing is proven


class VerifyServiceResult(BaseModel):
    service_proven: bool       # True = work was provably rendered → a refund must NOT auto-fire
    evidence_summary: str      # human-readable proof, shown to the dispute reviewer
    dispute_reason: str        # why this is a dispute, "" when not
    provider_state: str = "idle"   # booking.provider_state, for the refund-lock gate


async def verify_service(ctx: FunctionContext, data: VerifyServiceInput) -> VerifyServiceResult:
    pod = Pod.from_env()

    if not data.booking_id:
        return VerifyServiceResult(service_proven=False, evidence_summary="No booking linked.", dispute_reason="")

    booking = pod.table("bookings").get(data.booking_id)
    provider_state = booking.get("provider_state") or "idle"
    evidence = pod.records.list(
        "service_evidence", limit=50,
        filter=[{"field": "booking_id", "op": "eq", "value": data.booking_id}],
    ).to_dict()["items"]

    signals = []
    proven = False

    if booking.get("status") in ("in_progress", "completed"):
        proven = True
        signals.append(f"work status is '{booking['status']}'")
    if booking.get("check_in_at"):
        proven = True
        loc = booking.get("check_in_geo") or "address"
        signals.append(f"provider checked in at {booking['check_in_at']} ({loc})")
    if booking.get("start_otp_verified"):
        proven = True
        signals.append("client verified the START OTP (acknowledged arrival)")
    if booking.get("completion_otp_verified"):
        proven = True
        signals.append("client verified the COMPLETION OTP")

    photos = [e for e in evidence if e.get("kind") in ("before_photo", "after_photo")]
    if photos:
        proven = True
        signals.append(f"{len(photos)} service photo(s) on file")
    for e in evidence:
        if e.get("kind") == "arrival_checkin":
            proven = True
    # fold any extra evidence rows into the summary
    extra = [e["kind"] for e in evidence if e.get("kind") not in ("before_photo", "after_photo")]
    if extra:
        signals.append("evidence log: " + ", ".join(sorted(set(extra))))

    if proven:
        summary = "PROOF OF SERVICE FOUND — " + "; ".join(signals) + "."
        reason = ("Customer requested a refund, but the provider has proof the service was "
                  "rendered. Do not auto-refund — review the evidence before any payout.")
    else:
        summary = "No proof of service (provider had not arrived / no check-in or OTP)."
        reason = ""

    return VerifyServiceResult(service_proven=proven, evidence_summary=summary, dispute_reason=reason,
                                provider_state=provider_state)
