import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.jsonc import load

wf = load("workflows/handle_ticket/handle_ticket.json")
nodes = {n["id"]: n for n in wf["nodes"]}
assert "alert_provider" in nodes, "missing alert_provider node"

gate = nodes["gate"]["config"]["rules"]
conds = [r["condition"] for r in gate]
assert any("provider_state" in c and "refund" in c for c in conds), "refund lock missing provider_state"
assert any(r["next_node_id"] == "alert_provider" for r in gate), "no rule routes to alert_provider"

edges = wf["edges"]
out = [e["target"] for e in edges if e["source"] == "alert_provider"]
assert out and all(t in ("notify", "end") for t in out), f"alert_provider should go to notify/end, got {out}"
print("test_handle_ticket_graph OK")
