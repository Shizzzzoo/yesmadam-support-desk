import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests._load import load_fn

cer = load_fn("commit_en_route")
r = cer.build_customer_reply(pro_name="Karan", eta_minutes=15, on_site=False)
assert "Karan" in r and "15" in r
r2 = cer.build_customer_reply(pro_name="Karan", eta_minutes=0, on_site=True)
assert "on site" in r2.lower()

ofr = load_fn("offer_reschedule")
o = ofr.build_offer_reply(pro_name="Pooja", new_time="2026-06-30T18:00:00Z")
assert "Pooja" in o and "2026-06-30" in o and "yes" in o.lower()

ar = load_fn("apply_reschedule")
assert ar.is_valid_future("2099-01-01T00:00:00Z", "2026-06-25T00:00:00Z") is True
assert ar.is_valid_future("2020-01-01T00:00:00Z", "2026-06-25T00:00:00Z") is False
assert ar.is_valid_future("not-a-date", "2026-06-25T00:00:00Z") is False

# the other two import cleanly (no pure helper to assert)
load_fn("read_response"); load_fn("provider_stand_notice")
print("test_provider_funcs OK")
