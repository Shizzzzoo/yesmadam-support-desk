import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests._load import load_fn

mod = load_fn("alert_provider")

msg = mod.build_holding_reply(pro_name="Pooja", sla_minutes=5)
for token in ["Pooja", "5 minute", "refund"]:
    assert token.lower() in msg.lower(), token

assert mod.should_alert("idle") is True
assert mod.should_alert("stood_down") is True
assert mod.should_alert("alerted") is False
assert mod.should_alert("en_route") is False
print("test_alert_provider OK")
