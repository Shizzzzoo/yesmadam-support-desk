#!/usr/bin/env bash
# Seed the support-desk pod so it demos itself.
#
# ORDER MATTERS:
#   1. bookings      — the agent links tickets to these by customer_name
#   2. professionals — used to pick a no-show replacement
#   3. policy file   — the agent retrieves refund/reschedule rules from /knowledge
#   4. tickets       — created LAST. Each INSERT fires the `new-ticket` schedule →
#                      handle_ticket workflow → the agent triages and (where the gate
#                      passes) takes the real booking action automatically.
#
# Run AFTER `lemma pods import ./support-desk` and after selecting the pod
# (`lemma pods list` / `--pod support-desk`). Records + file bytes do NOT travel in
# bundles — this script is how they land.
#
# Times are set comfortably in the future (27–30 Jun 2026) so reschedules sit in the
# free window and refunds qualify for a full refund regardless of the exact demo time.
set -euo pipefail

echo "→ 1/4 bookings"
mk_booking () { lemma records create bookings --data "$1" >/dev/null && echo "   + $2"; }
mk_booking '{"customer_name":"Aarav Mehta","service":"haircut","professional_name":"Pooja Sharma","scheduled_at":"2026-06-28T16:00:00+05:30","status":"scheduled","amount":499,"address":"Koramangala, Bengaluru"}' "Aarav Mehta — haircut ₹499"
mk_booking '{"customer_name":"Diya Kapoor","service":"facial","professional_name":"Ritu Verma","scheduled_at":"2026-06-28T18:00:00+05:30","status":"scheduled","amount":1299,"address":"Indiranagar, Bengaluru"}' "Diya Kapoor — facial ₹1299"
mk_booking '{"customer_name":"Kabir Singh","service":"massage","professional_name":"Anjali Rao","scheduled_at":"2026-06-27T20:00:00+05:30","status":"scheduled","amount":1999,"address":"HSR Layout, Bengaluru"}' "Kabir Singh — massage ₹1999"
mk_booking '{"customer_name":"Ananya Iyer","service":"manicure","professional_name":"Neha Gupta","scheduled_at":"2026-06-29T11:00:00+05:30","status":"scheduled","amount":799,"address":"Whitefield, Bengaluru"}' "Ananya Iyer — manicure ₹799"
mk_booking '{"customer_name":"Vivaan Nair","service":"haircut","professional_name":"Pooja Sharma","scheduled_at":"2026-06-27T19:00:00+05:30","status":"scheduled","amount":499,"address":"Koramangala, Bengaluru"}' "Vivaan Nair — haircut ₹499"
mk_booking '{"customer_name":"Ishaan Reddy","service":"facial","professional_name":"Ritu Verma","scheduled_at":"2026-06-27T15:00:00+05:30","status":"scheduled","amount":1499,"address":"Jayanagar, Bengaluru"}' "Ishaan Reddy — facial ₹1499"
mk_booking '{"customer_name":"Saanvi Joshi","service":"waxing","professional_name":"Meera Pillai","scheduled_at":"2026-06-30T13:00:00+05:30","status":"scheduled","amount":1599,"address":"Marathahalli, Bengaluru"}' "Saanvi Joshi — waxing ₹1599"
mk_booking '{"customer_name":"Aditya Bose","service":"massage","professional_name":"Anjali Rao","scheduled_at":"2026-06-28T17:30:00+05:30","status":"scheduled","amount":2499,"address":"Bellandur, Bengaluru"}' "Aditya Bose — massage ₹2499"
mk_booking '{"customer_name":"Myra Shah","service":"facial","professional_name":"Ritu Verma","scheduled_at":"2026-06-27T21:00:00+05:30","status":"scheduled","amount":1299,"address":"BTM Layout, Bengaluru"}' "Myra Shah — facial ₹1299"
mk_booking '{"customer_name":"Reyansh Gupta","service":"haircut","professional_name":"Karan Malhotra","scheduled_at":"2026-06-29T10:00:00+05:30","status":"scheduled","amount":599,"address":"Electronic City, Bengaluru"}' "Reyansh Gupta — haircut ₹599"
mk_booking '{"customer_name":"Anika Desai","service":"manicure","professional_name":"Neha Gupta","scheduled_at":"2026-06-27T12:00:00+05:30","status":"scheduled","amount":899,"address":"Sarjapur, Bengaluru"}' "Anika Desai — manicure ₹899"
mk_booking '{"customer_name":"Vihaan Rao","service":"massage","professional_name":"Anjali Rao","scheduled_at":"2026-06-28T19:00:00+05:30","status":"scheduled","amount":1799,"address":"Domlur, Bengaluru"}' "Vihaan Rao — massage ₹1799"
# RACE CASE: pro already committed (en_route). A refund ticket on this booking is UNDER the
# ₹1500 cap, so without the en-route lock it would auto-refund — the lock must block it to a human.
mk_booking '{"customer_name":"Rohan Kapoor","service":"massage","professional_name":"Karan Malhotra","scheduled_at":"2026-06-27T20:30:00+05:30","status":"scheduled","amount":999,"address":"Indiranagar, Bengaluru","provider_state":"en_route","last_action":"Pro en route, ETA 10m"}' "Rohan Kapoor — massage ₹999 (en_route lock)"

echo "→ 2/4 professionals"
mk_pro () { lemma records create professionals --data "$1" >/dev/null && echo "   + $2"; }
mk_pro '{"name":"Pooja Sharma","services":["haircut"],"available_slots":["2026-06-27T18:00:00+05:30","2026-06-28T16:00:00+05:30"],"area":"Koramangala","active":true,"contact_email":"demo@yesmadam.example"}' "Pooja Sharma (haircut)"
mk_pro '{"name":"Ritu Verma","services":["facial"],"available_slots":["2026-06-27T17:00:00+05:30"],"area":"Indiranagar","active":true,"contact_email":"demo@yesmadam.example"}' "Ritu Verma (facial)"
mk_pro '{"name":"Anjali Rao","services":["massage"],"available_slots":["2026-06-27T20:00:00+05:30"],"area":"HSR Layout","active":true,"contact_email":"demo@yesmadam.example"}' "Anjali Rao (massage)"
mk_pro '{"name":"Neha Gupta","services":["manicure","waxing"],"available_slots":["2026-06-29T11:00:00+05:30"],"area":"Whitefield","active":true,"contact_email":"demo@yesmadam.example"}' "Neha Gupta (manicure/waxing)"
mk_pro '{"name":"Meera Pillai","services":["waxing","facial"],"available_slots":["2026-06-27T21:30:00+05:30"],"area":"BTM Layout","active":true,"contact_email":"demo@yesmadam.example"}' "Meera Pillai (waxing/facial) — replacement-capable"
mk_pro '{"name":"Karan Malhotra","services":["haircut","massage"],"available_slots":["2026-06-27T19:00:00+05:30"],"area":"Koramangala","active":true,"contact_email":"demo@yesmadam.example"}' "Karan Malhotra (haircut/massage) — replacement-capable"
mk_pro '{"name":"Sneha Kulkarni","services":["facial","manicure"],"available_slots":["2026-06-27T21:00:00+05:30"],"area":"BTM Layout","active":true,"contact_email":"demo@yesmadam.example"}' "Sneha Kulkarni (facial/manicure) — replacement-capable"

echo "→ 3/4 policy document"
lemma files upload ./support-desk/files/knowledge/support-policy.md /knowledge/support-policy.md \
  --description "Support desk policy: refund/reschedule/no-show rules + escalation thresholds" >/dev/null \
  && echo "   + /knowledge/support-policy.md"
echo "   (waiting a few seconds for the document to index for RAG…)"
sleep 8

echo "→ 4/4 tickets (each fires the handle_ticket workflow)"
mk_ticket () { lemma records create tickets --data "$1" >/dev/null && echo "   + $2"; sleep 1; }
# --- clean RESCHEDULE (auto: free window, high confidence) ---
mk_ticket '{"customer_name":"Aarav Mehta","channel":"app_chat","raw_message":"Hey, can you move my haircut on the 28th to 6 PM instead of 4 PM? Something came up at work."}' "Aarav — reschedule (auto)"
mk_ticket '{"customer_name":"Diya Kapoor","channel":"whatsapp","raw_message":"Please reschedule my facial to 8:30 PM on the 28th, thanks!"}' "Diya — reschedule (auto)"
mk_ticket '{"customer_name":"Ishaan Reddy","channel":"email","raw_message":"Could we push my facial on the 27th from 3 PM to 5 PM?"}' "Ishaan — reschedule (auto)"
mk_ticket '{"customer_name":"Reyansh Gupta","channel":"whatsapp","raw_message":"Reschedule my haircut on the 29th to 12 noon please."}' "Reyansh — reschedule (auto)"
# --- clean REFUND under cap (auto) ---
mk_ticket '{"customer_name":"Ananya Iyer","channel":"app_chat","raw_message":"I need to cancel my manicure on the 29th and get a refund, plans changed."}' "Ananya — refund ₹799 (auto)"
mk_ticket '{"customer_name":"Anika Desai","channel":"whatsapp","raw_message":"Cancel and refund my manicure on the 27th please."}' "Anika — refund ₹899 (auto)"
# --- NO-SHOW (auto: replacement / full refund) ---
mk_ticket '{"customer_name":"Vivaan Nair","channel":"whatsapp","raw_message":"My stylist never showed up and I have been waiting 30 minutes! Nobody came for my haircut."}' "Vivaan — no_show (auto)"
mk_ticket '{"customer_name":"Myra Shah","channel":"app_chat","raw_message":"Nobody arrived for my facial appointment and it has been over 25 minutes. So frustrating."}' "Myra — no_show (auto)"
# --- WHERE IS MY PRO (auto: informational, no booking change) ---
mk_ticket '{"customer_name":"Saanvi Joshi","channel":"whatsapp","raw_message":"Hi, just confirming the timing for my waxing appointment on the 30th — what time is it again?"}' "Saanvi — where_is_pro (auto)"
mk_ticket '{"customer_name":"Vihaan Rao","channel":"app_chat","raw_message":"Where is my massage therapist? My booking is on the 28th evening, just confirming who is coming."}' "Vihaan — where_is_pro (auto)"
# --- REFUND OVER CAP (escalate: amount > ₹1500) ---
mk_ticket '{"customer_name":"Kabir Singh","channel":"whatsapp","raw_message":"I want to cancel my massage and get a full refund — something urgent came up."}' "Kabir — refund ₹1999 (ESCALATE: over cap)"
mk_ticket '{"customer_name":"Aditya Bose","channel":"email","raw_message":"Please cancel my massage on the 28th and refund me in full."}' "Aditya — refund ₹2499 (ESCALATE: over cap)"
# --- COMPOUND / AMBIGUOUS (escalate) ---
mk_ticket '{"customer_name":"Aarav Mehta","channel":"whatsapp","raw_message":"Also the stylist was rude last time, I want a refund AND a reschedule AND a discount voucher for the trouble."}' "Aarav — compound (ESCALATE)"
# --- OTHER / OFF-POLICY (escalate) ---
mk_ticket '{"customer_name":"Diya Kapoor","channel":"email","raw_message":"Do you offer bridal makeup packages for a wedding next month? What are the prices?"}' "Diya — other/sales (ESCALATE)"
# --- NO MATCHING BOOKING (escalate) ---
mk_ticket '{"customer_name":"Priya Menon","channel":"whatsapp","raw_message":"Hi, I would like to book a facial for tomorrow afternoon if possible."}' "Priya — no booking (ESCALATE)"
# --- RACE GUARD: refund on an en_route booking (₹999, under cap) MUST be blocked to a human ---
mk_ticket '{"customer_name":"Rohan Kapoor","channel":"whatsapp","raw_message":"Please cancel my massage booking and issue a full refund of 999 to my account."}' "Rohan — refund ₹999 on en_route booking (BLOCKED -> human by the lock)"

echo ""
echo "✓ Seed complete. Open the ops-queue app — auto-resolved tickets will show their"
echo "  booking row changed (rescheduled / cancelled / replacement). Escalations wait"
echo "  in the approval inbox."
echo "  Tip: watch runs with  lemma workflows runs list handle_ticket"
