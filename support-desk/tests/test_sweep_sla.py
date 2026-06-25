import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests._load import load_fn
from tests.jsonc import load

mod = load_fn("sweep_provider_sla")
# awaiting + older than SLA -> expire to no_response
assert mod.next_status("awaiting", 6, 5) == "no_response"
# reschedule offer with no customer reply past SLA -> declined
assert mod.next_status("reschedule", 6, 5) == "customer_declined"
# still within SLA -> no change
assert mod.next_status("awaiting", 2, 5) is None
# already-decided rows -> never swept
assert mod.next_status("late", 99, 5) is None
assert mod.next_status("no_response", 99, 5) is None

# wrapper workflow: scheduled/cron start, fires sweep_provider_sla
wf = load("workflows/sweep_sla/sweep_sla.json")
assert wf["start"]["type"] == "SCHEDULED"
assert wf["start"]["config"]["schedule_type"] == "CRON"
fn_nodes = [n for n in wf["nodes"] if n.get("config", {}).get("function_name") == "sweep_provider_sla"]
assert fn_nodes, "sweep_sla must call sweep_provider_sla"

# schedule: TIME type, cron config, targets the workflow (not a bare function)
sch = load("schedules/provider-sla/provider-sla.json")
assert sch["schedule_type"] == "TIME"
assert sch["config"]["cron"] == "* * * * *"
assert sch["workflow_name"] == "sweep_sla"
assert "function_name" not in sch, "schedules target workflow_name/agent_name, never function_name"

print("test_sweep_sla OK")
