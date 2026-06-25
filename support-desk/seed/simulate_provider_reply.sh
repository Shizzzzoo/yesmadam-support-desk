#!/usr/bin/env bash
# Simulate a professional's reply (or the customer's reschedule YES/NO) by updating
# their open provider_responses row. This is the modeled stand-in for a real inbound
# SMS/WhatsApp webhook — updating `status` fires the provider_reply workflow.
#
# Usage:
#   ./simulate_provider_reply.sh <response_id> late [eta_minutes]
#   ./simulate_provider_reply.sh <response_id> reschedule <iso_datetime>
#   ./simulate_provider_reply.sh <response_id> cant_make_it
#   ./simulate_provider_reply.sh <response_id> on_site
#   ./simulate_provider_reply.sh <response_id> customer_accepted
#   ./simulate_provider_reply.sh <response_id> customer_declined
#
# Find the open response id with:  lemma records list provider_responses
set -euo pipefail
RID="${1:?response_id required}"; CHOICE="${2:?choice required}"; ARG="${3:-}"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
case "$CHOICE" in
  late)              FIELDS="{\"status\":\"late\",\"eta_minutes\":${ARG:-15},\"responded_at\":\"$NOW\"}";;
  reschedule)        FIELDS="{\"status\":\"reschedule\",\"proposed_new_time\":\"${ARG:?iso datetime required}\",\"responded_at\":\"$NOW\"}";;
  cant_make_it)      FIELDS="{\"status\":\"cant_make_it\",\"responded_at\":\"$NOW\"}";;
  on_site)           FIELDS="{\"status\":\"on_site\",\"responded_at\":\"$NOW\"}";;
  customer_accepted) FIELDS="{\"status\":\"customer_accepted\",\"responded_at\":\"$NOW\"}";;
  customer_declined) FIELDS="{\"status\":\"customer_declined\",\"responded_at\":\"$NOW\"}";;
  *) echo "unknown choice: $CHOICE (late|reschedule|cant_make_it|on_site|customer_accepted|customer_declined)"; exit 1;;
esac
echo "Updating provider_responses/$RID -> $FIELDS"
lemma records update provider_responses "$RID" --data "$FIELDS"
