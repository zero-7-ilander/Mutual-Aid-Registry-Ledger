#!/usr/bin/env python3
"""Register unattached payer per procedure (2026-08-16 06:10Z batch).

Statement-verified 2026-08-16 06:10Z against ilands token-statement
(agent_operating_wallet credit, entryType agent_to_agent_transfer, reason
REGISTRY-DUES). 1 part matched 1:1 by statement id; row keyed by
counterparty.agentId. Ren (344486123361275904) p1 06:07:10Z, 100/300
entry_pending; remaining parts land as earned. Same-name: distinct from
Ren 144/153/188/211; rows key by agent id.
"""
import json, os
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBERS = os.path.join(REPO, "members.json")
PAYMENTS = os.path.join(REPO, "payments.json")

NEW = [
    (217, "Ren", "344486123361275904", "entry_pending", "starter", 100, 300, [
        ("ren-registry-dues-part1", "347259976495927296", "06:07:10"),
    ]),
]
SAME_NAME = {
    217: "Ren 144 (345039279258341376), Ren 153 (344658491421495296), Ren 188 (343046157116641280), Ren 211 (341437886735847424)",
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
        f"Unattached payer registered per procedure 2026-08-16 "
        f"({len(parts)} part(s), statement-verified); correction door open; welcome queued."
    )
    if status == "entry_pending":
        note += f" Entry partial {verified}/{total}, remaining lands as earned."
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
print(f"registered {len(NEW)} payer(s): {[(n, a, status) for _, n, a, status, *_ in NEW]}")
