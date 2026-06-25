import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests._load import load_fn

mod = load_fn("notify_provider")
body = mod.build_alert_body(customer_name="Vivaan", service="haircut",
                            address="Koramangala", scheduled="Sat 7:00 pm",
                            sla_minutes=5)
for token in ["Vivaan", "haircut", "Koramangala", "5 minute",
              "running late", "reschedule", "can't make it", "on site"]:
    assert token.lower() in body.lower(), f"alert body missing: {token}"
print("test_notify_provider OK")
