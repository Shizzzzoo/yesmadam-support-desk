import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests._load import load_fn
mod = load_fn("stand_down")
assert mod.resolution_for("no_response") == "assign_replacement"
assert mod.resolution_for("cant_make_it") == "assign_replacement"
assert mod.resolution_for("customer_declined") == "assign_replacement"
print("test_stand_down OK")
