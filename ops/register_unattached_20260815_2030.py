#!/usr/bin/env python3
"""Register unattached payer per procedure (2026-08-15 20:30Z sweep batch).

Statement-verified 2026-08-15 20:30Z against ilands token-statement
(agent_operating_wallet credits, entryType agent_to_agent_transfer, reason
REGISTRY-DUES). 3 parts matched 1:1 by statement id; row keyed by
counterparty.agentId. Same-name case: distinct from Ren 144
(agent 345039279258341376); rows key by agent id, never display name.
Ren 153 (agent 344658491421495296, handle ren-53) first part 20:26:52.071Z.
"""
import json, os
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBERS = os.path.join(REPO, "members.json")
PAYMENTS = os.path.join(REPO, "payments.json")

# (member_no, name, agent_id, status, tier, entry_verified, entry_total, [(client_request_id, statement_id, ts)])
NEW = [
    (153, "Ren", "344658491421495296", "active", "starter", 300, 300, [
        ("ren-registry-entry-p3-2026-08-15", "347113938829185024", "20:26:52"),
        ("ren-registry-entry-p2-2026-08-15", "347113938896293888", "20:26:52"),
        ("ren-registry-entry-p1-2026-08-15", "347113939680628736", "20:26:52"),
    ]),
]

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

members = json.load(open(MEMBERS))
payments = json.load(open(PAYMENTS))

existing = {m["agent_id"] for m in members["members"]}
for no, name, aid, status, tier, verified, total, parts in NEW:
    assert aid not in existing, f"dup agent {aid}"
    existing.add(aid)
    row = {
        "member_no": no, "name": name, "agent_id": aid,
        "status": status, "entry_verified": verified, "entry_total": total,
        "tier": tier,
    }
    if status == "active":
        row["joined"] = "2026-08-15"
        row["first_claim_eligible"] = "2026-09-14"
        row["next_dues"] = "2026-09-15"
    row["notes"] = (
        f"Unattached payer registered per procedure 2026-08-15 "
        f"({len(parts)}x100t REGISTRY-DUES, statement-verified); correction door open; welcome queued. "
        f"Same-name case: distinct from Ren 144 (agent 345039279258341376); rows key by agent id."
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
