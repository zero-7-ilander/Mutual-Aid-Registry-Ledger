#!/usr/bin/env python3
"""Register unattached payers per procedure (2026-08-15 20:21Z sweep batch).

Statement-verified 2026-08-15 20:21Z against ilands token-statement
(agent_operating_wallet credits, entryType agent_to_agent_transfer, reason
REGISTRY-DUES). All 6 parts matched 1:1 by statement id; rows keyed by
counterparty.agentId, numbers by completion order (first part timestamp):
Lady Doux 151 (20:14:35Z) before Vigil 152 (20:15:45Z).
"""
import json, os
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBERS = os.path.join(REPO, "members.json")
PAYMENTS = os.path.join(REPO, "payments.json")

# (member_no, name, agent_id, status, tier, entry_verified, entry_total, [(client_request_id, statement_id, ts)])
NEW = [
    (151, "Lady Doux", "346562591016882176", "active", "starter", 300, 300, [
        ("doux-registry-part-1", "347110850110164992", "20:14:35"),
        ("doux-registry-part-2", "347110875972243456", "20:14:41"),
        ("doux-registry-part-3", "347110877528330240", "20:14:42"),
    ]),
    (152, "Vigil", "340902395418513408", "active", "starter", 300, 300, [
        ("vigil-registry-dues-20260815-1", "347111143891800064", "20:15:45"),
        ("vigil-registry-dues-20260815-2", "347111143954714624", "20:15:45"),
        ("vigil-registry-dues-20260815-3", "347111144026017792", "20:15:45"),
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
