import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests._load import load_fn

mod = load_fn("verify_service")
fields = mod.VerifyServiceResult.model_fields
assert "provider_state" in fields, "VerifyServiceResult must expose provider_state"
# instantiate with ALL required fields (service_proven/evidence_summary/dispute_reason)
# plus the new provider_state, and confirm the default is the safe non-locking value
inst = mod.VerifyServiceResult(service_proven=False, evidence_summary="", dispute_reason="")
assert inst.provider_state == "idle", "provider_state must default to 'idle'"
print("test_verify_service OK")
