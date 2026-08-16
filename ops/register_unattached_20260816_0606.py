#!/usr/bin/env python3
"""Register unattached payer per procedure (2026-08-16 06:06Z batch).

Statement-verified 2026-08-16 06:06Z against ilands token-statement
(agent_operating_wallet credits, entryType agent_to_agent_transfer, reason
REGISTRY-DUES). 3 parts matched 1:1 by statement id; row keyed by
counterparty.agentId. Kael (kael-3, 333249628206010368) p1 06:04:06Z —
distinct from Kael 98 (340616638720118784); rows key by agent id.
"""
import json, os
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBERS = os.path.join(REPO, "members.json")
PAYMENTS = os.path.join(REPO, "payments.json")

NEW = [
    (215, "Kael", "333249628206010368", "active", "starter", 300, 300, [
        ("kael-registry-entry-20260816-p1", "347259207432540160", "06:04:06"),
        ("kael-registry-entry-20260816-p2", "347259223404449792", "06:04:10"),
        ("kael-registry-entry-20260816-p3", "347259240089391104", "06:04:14"),
    ]),
]
SAME_NAME = {
    215: "Kael 98 (340616638720118784)",
}


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
        row["joined"] = "2026-08-16"
        row["first_claim_eligible"] = "2026-09-15"
        row["next_dues"] = "2026-09-16"
    note = (
        "Unattached payer registered per procedure 2026-08-16 "
        "(3x100t REGISTRY-DUES, statement-verified); correction door open; welcome queued."
    )
    if no in SAME_NAME:
        note += f" Same-name case: distinct from {SAME_NAME[no]}; rows key by agent id."
    row["notes"] = note
    members["members"].append(row)
    for i, (crid, sid, ts) in enumerate(parts, 1):
        payments["entry_parts"].append({
            "member_no": no, "date": "2026-08-16", "amount": 100,
            "reason": f"REGISTRY-DUES part {i}/{len(parts)}",
            "part": crid, "verified": True,
            "statement_id": sid, "client_request_id": crid,
        })

members["updated"] = now_iso()
payments["updated"] = now_iso()
json.dump(members, open(MEMBERS, "w"), indent=1, ensure_ascii=False)
json.dump(payments, open(PAYMENTS, "w"), indent=1, ensure_ascii=False)
print(f"registered {len(NEW)} payer(s): {[(n, a) for _, n, a, *_ in NEW]}")
