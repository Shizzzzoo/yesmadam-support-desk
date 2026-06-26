import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.jsonc import load

cfg = load("apps/customer-chat/customer-chat.json")
assert cfg["name"] == "customer-chat"
assert cfg.get("public_slug"), "needs a public_slug for the URL"

html = open("apps/customer-chat/html.html").read()
assert "LemmaClient" in html, "must use the browser LemmaClient"
assert "concierge" in html, "must target the concierge agent"
assert "sendMessage" in html, "must have a send-message handler"
print("test_customer_chat OK")
