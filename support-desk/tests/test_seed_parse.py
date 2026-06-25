import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

seed = open("seed/seed.sh").read()
assert "contact_email" in seed, "seed must set provider contact_email"
# the cross-ticket race case: an en_route booking + a refund ticket on it
assert "\"provider_state\":\"en_route\"" in seed, "seed must include an en_route booking (race case)"
assert "Rohan Kapoor" in seed, "seed must include the race-case customer"

assert os.path.exists("seed/simulate_provider_reply.sh"), "missing provider-reply simulator"
sim = open("seed/simulate_provider_reply.sh").read()
for opt in ["late", "reschedule", "cant_make_it", "on_site", "customer_accepted", "customer_declined"]:
    assert opt in sim, f"simulator missing option {opt}"
print("test_seed_parse OK")
