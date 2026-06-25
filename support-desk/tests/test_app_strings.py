html = open("apps/ops-queue/html.html").read()
assert "awaiting_provider" in html, "app must render the awaiting_provider status"
assert "provider_state" in html and "en_route" in html, "app must show the en-route lock"
assert "provider_responses" in html, "app must load/watch provider_responses"
assert "Provider coordination" in html, "app must show the coordination block"
assert "min left before auto-refund" in html, "app must show the SLA countdown"
print("test_app_strings OK")
