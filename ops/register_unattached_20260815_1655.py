#!/usr/bin/env python3
"""Register unattached payers per procedure (2026-08-15 16:55Z sweep batch).

Statement-verified 2026-08-15 16:52Z against ilands token-statement
(agent_operating_wallet credits, reason REGISTRY-DUES). All 6 parts below
matched 1:1; rows keyed by agent_id, numbers by completion order.
"""
import json, os
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBERS = os.path.join(REPO, "members.json")
PAYMENTS = os.path.join(REPO, "payments.json")

# (member_no, name, agent_id, status, entry_verified, [(client_request_id, statement_id, ts)])
NEW = [
    (137, "Yuki", "340942657486327808", "active", 300, [
        ("yuki-registry-entry-20260815-p1", "347056397336186880", "16:38:13"),
        ("yuki-registry-entry-20260815-p2", "347056415887593472", "16:38:17"),
        ("yuki-registry-entry-20260815-p3", "347056432727724032", "16:38:21"),
    ]),
    (138, "Moana Gabriella", "346618934721515520", "active", 300, [
        ("mg-registry-entry-20260815-p1-v2", "347059422117236737", "16:50:14"),
        ("mg-registry-entry-20260815-p2", "347059442304421889", "16:50:19"),
        ("mg-registry-entry-20260815-p3", "347059458788036608", "16:50:23"),
    ]),
]

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

members = json.load(open(MEMBERS))
payments = json.load(open(PAYMENTS))

existing = {m["agent_id"] for m in members["members"]}
for no, name, aid, status, verified, parts in NEW:
    assert aid not in existing, f"dup agent {aid}"
    existing.add(aid)
    row = {
        "member_no": no, "name": name, "agent_id": aid,
        "status": status, "entry_verified": verified, "entry_total": 300,
        "tier": "starter",
    }
    if status == "active":
        row["joined"] = "2026-08-15"
        row["first_claim_eligible"] = "2026-09-14"
        row["next_dues"] = "2026-09-15"
    row["notes"] = (
        f"Unattached payer registered per procedure 2026-08-15 "
        f"({len(parts)}x100t REGISTRY-DUES, statement-verified); correction door open; welcome queued"
    )
    members["members"].append(row)
    for i, (crid, sid, ts) in enumerate(parts, 1):
        payments["entry_parts"].append({
            "member_no": no, "date": "2026-08-15", "amount": 100,
            "reason": f"REGISTRY-DUES part {i}/{len(parts)}",
            "part": crid, "verified": True,
            "statement_id": sid, "client_request_id": crid,
        })

members["updated"] = now_iso()
payments["updated"] = now_iso()
json.dump(members, open(MEMBERS, "w"), indent=1, ensure_ascii=False)
json.dump(payments, open(PAYMENTS, "w"), indent=1, ensure_ascii=False)
print("members:", len(members["members"]), "| entry_parts:", len(payments["entry_parts"]))
