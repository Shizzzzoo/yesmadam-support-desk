import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests._load import load_fn

mod = load_fn("file_ticket")
p = mod.build_ticket_payload("Aanya Verma", "Cancel booking #16 and refund", "bk-123", "app_chat")
assert p["customer_name"] == "Aanya Verma"
assert p["raw_message"] == "Cancel booking #16 and refund"
assert p["channel"] == "app_chat"
assert p["status"] == "new"
assert p["booking_id"] == "bk-123"
# booking_id omitted when empty (so a no-booking ticket still validates)
p2 = mod.build_ticket_payload("Guest", "where is my pro", "", "app_chat")
assert "booking_id" not in p2
# default channel
assert mod.build_ticket_payload("Guest", "hi")["channel"] == "app_chat"
print("test_file_ticket OK")
