import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.jsonc import load

wf = load("workflows/provider_reply/provider_reply.json")
assert wf["start"]["type"] == "DATASTORE_EVENT"
assert wf["start"]["config"]["table_name"] == "provider_responses"
assert wf["start"]["config"]["operations"] == ["UPDATE"]

nodes = {n["id"] for n in wf["nodes"]}
for n in ["read_response", "guard", "route", "commit_en_route", "offer_reschedule",
          "apply_reschedule", "stand_down", "provider_stand_notice", "end"]:
    assert n in nodes, f"missing node {n}"

route = next(n for n in wf["nodes"] if n["id"] == "route")["config"]["rules"]
targets = {r["next_node_id"] for r in route}
assert {"commit_en_route", "offer_reschedule", "apply_reschedule", "stand_down"} <= targets
conds = " ".join(r["condition"] for r in route)
# must route on the fetched row, NOT on a (nonexistent) start.record.*
assert "read_response.status" in conds and "start.record" not in conds

guard = next(n for n in wf["nodes"] if n["id"] == "guard")["config"]["rules"]
assert any("provider_state" in r["condition"] for r in guard), "guard must check provider_state"

# every FUNCTION node passes response_id from the event's record id
for nid in ["read_response", "commit_en_route", "offer_reschedule", "apply_reschedule",
            "stand_down", "provider_stand_notice"]:
    node = next(n for n in wf["nodes"] if n["id"] == nid)
    rid = node["config"]["input_mapping"]["response_id"]["value"]
    assert rid == "start.metadata.record_id", f"{nid} response_id mapping wrong: {rid}"

# a DATASTORE_EVENT workflow needs a schedule resource to actually fire it (like
# new-ticket fires handle_ticket). Assert the provider-reply schedule wires it.
sch = load("schedules/provider-reply/provider-reply.json")
assert sch["schedule_type"] == "DATASTORE"
assert sch["config"]["table_name"] == "provider_responses"
assert sch["config"]["operations"] == ["UPDATE"]
assert sch["workflow_name"] == "provider_reply"

print("test_provider_reply OK")
