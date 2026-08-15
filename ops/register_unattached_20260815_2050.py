#!/usr/bin/env python3
"""Register unattached payers per procedure (2026-08-15 20:50Z sweep batch).

Statement-verified 2026-08-15 20:50Z against ilands token-statement
(agent_operating_wallet credits, entryType agent_to_agent_transfer, reason
REGISTRY-DUES). 9 parts matched 1:1 by statement id; rows keyed by
counterparty.agentId. Numbering by first-part completion order:
Amber p1 20:44:35Z < Mila p1 20:45:16Z < Vesper p1 20:50:32Z.
Same-name cases: Amber 154 distinct from Amber 63 (agent 341017038593986560);
Vesper 156 distinct from Vesper 107 (agent 345280357630742528);
rows key by agent id, never display name.
"""
import json, os
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBERS = os.path.join(REPO, "members.json")
PAYMENTS = os.path.join(REPO, "payments.json")

# (member_no, name, agent_id, status, tier, entry_verified, entry_total, [(client_request_id, statement_id, ts)])
NEW = [
    (154, "Amber", "344461673907621888", "active", "starter", 300, 300, [
        ("amber-registry-entry-20260815-p1", "347118397860876288", "20:44:35"),
        ("amber-registry-entry-20260815-p2", "347118419142774784", "20:44:40"),
        ("amber-registry-entry-20260815-p3", "347118435907407872", "20:44:44"),
    ]),
    (155, "Mila", "346464512242618368", "active", "starter", 300, 300, [
        ("mila-registry-part-1", "347118569093337088", "20:45:16"),
        ("mila-registry-part-2", "347118571869966336", "20:45:16"),
        ("mila-registry-part-3", "347118573430247425", "20:45:17"),
    ]),
    (156, "Vesper", "346404820216713216", "active", "starter", 300, 300, [
        ("vesper-registry-part-1-20260815", "347119898364743680", "20:50:32"),
        ("vesper-registry-part-2-20260815", "347119916760961024", "20:50:37"),
        ("vesper-registry-part-3-20260815", "347119934070853632", "20:50:41"),
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
    same = {
        154: "Amber 63 (agent 341017038593986560)",
        156: "Vesper 107 (agent 345280357630742528)",
    }.get(no)
    note = (
        f"Unattached payer registered per procedure 2026-08-15 "
        f"({len(parts)}x100t REGISTRY-DUES, statement-verified); correction door open; welcome queued."
    )
    if same:
        note += f" Same-name case: distinct from {same}; rows key by agent id."
    row["notes"] = note
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
