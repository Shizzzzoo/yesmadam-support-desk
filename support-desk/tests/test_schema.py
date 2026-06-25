import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.jsonc import load

pr = load("tables/provider_responses/provider_responses.json")
assert pr["name"] == "provider_responses"
cols = {c["name"]: c for c in pr["columns"]}
for c in ["ticket_id", "booking_id", "professional_name", "status",
          "eta_minutes", "proposed_new_time", "alerted_at", "responded_at", "note"]:
    assert c in cols, f"missing column {c}"
assert set(cols["status"]["options"]) == {
    "awaiting", "late", "reschedule", "on_site", "cant_make_it",
    "no_response", "customer_accepted", "customer_declined"}
assert cols["status"]["default"] == "awaiting"

bk = {c["name"]: c for c in load("tables/bookings/bookings.json")["columns"]}
assert bk["provider_state"]["default"] == "idle"
assert set(bk["provider_state"]["options"]) == {"idle", "alerted", "en_route", "stood_down"}

pro = {c["name"]: c for c in load("tables/professionals/professionals.json")["columns"]}
assert "contact_email" in pro

tk = {c["name"]: c for c in load("tables/tickets/tickets.json")["columns"]}
# awaiting-provider tickets are parked as the existing "triaged" status — Lemma can't
# extend an existing ENUM column's options on a live table without dropping it. The
# "awaiting" semantics live on the provider_responses row + booking.provider_state.
assert "triaged" in tk["status"]["options"]
print("test_schema OK")
