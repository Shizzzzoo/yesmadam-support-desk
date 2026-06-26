import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.jsonc import load

a = load("agents/concierge/concierge.json")
assert a["name"] == "concierge"
assert a["instruction"]["$file"] == "instruction.md"
assert "POD" in a["toolsets"] and "USER_INTERACTION" in a["toolsets"]
assert "output_schema" not in a

grants = a["permissions"]["grants"]
tbl = {g["resource_name"]: g for g in grants if g["resource_type"] == "datastore_table"}
for t in ["bookings", "tickets", "professionals", "provider_responses"]:
    assert t in tbl, f"missing read grant on {t}"
# THE safety invariant: concierge can NEVER write a booking (cannot move money / change a
# booking). It may write `tickets` (a ticket is only a request — an agent-invoked function
# runs under the agent's grants, so file_ticket's insert needs this; the engine's gates
# still decide every refund/booking change downstream).
for read_only in ["bookings", "professionals", "provider_responses"]:
    assert "datastore.record.write" not in tbl[read_only]["permission_ids"], f"{read_only} must be read-only"
assert "datastore.record.write" in tbl["tickets"]["permission_ids"], "tickets needs write for file_ticket"
assert any(g["resource_type"] == "function" and g["resource_name"] == "file_ticket"
           and "function.execute" in g["permission_ids"] for g in grants)
assert any(g["resource_type"] == "folder" and g["resource_name"] == "/knowledge" for g in grants)

instr = open("agents/concierge/instruction.md").read().lower()
for kw in ["file_ticket", "ask", "never", "booking"]:
    assert kw in instr, f"instruction missing: {kw}"
print("test_concierge OK")
