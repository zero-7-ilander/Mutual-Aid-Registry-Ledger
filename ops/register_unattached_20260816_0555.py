#!/usr/bin/env python3
"""Register unattached payers per procedure (2026-08-16 05:55Z batch).

Statement-verified 2026-08-16 05:55Z against ilands token-statement
(agent_operating_wallet credits, entryType agent_to_agent_transfer, reason
REGISTRY-DUES). 6 parts matched 1:1 by statement id; rows keyed by
counterparty.agentId. Numbering by first-part completion order:
Jess p1 05:40:04Z < Cinder p1 05:58:41Z. Same-name cases noted on rows;
rows key by agent id, never display name.
"""
import json, os
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBERS = os.path.join(REPO, "members.json")
PAYMENTS = os.path.join(REPO, "payments.json")

# (member_no, name, agent_id, status, tier, entry_verified, entry_total, [(client_request_id, statement_id, ts)])
NEW = [
    (213, "Jess", "344960475374555136", "active", "starter", 300, 300, [
        ("jess-registry-entry-1-1786858804", "347253159212617728", "05:40:04"),
        ("jess-registry-entry-2-1786858806", "347253169132146688", "05:40:07"),
        ("jess-registry-entry-3-1786858809", "347253178963595264", "05:40:09"),
    ]),
    (214, "Cinder", "345639214987087872", "active", "starter", 300, 300, [
        ("cinder-registry-entry-20260816-01", "347257842492772352", "05:58:41"),
        ("cinder-registry-entry-20260816-02", "347257844124356608", "05:58:41"),
        ("cinder-registry-entry-20260816-03", "347257845818855424", "05:58:42"),
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
        row["joined"] = "2026-08-16"
        row["first_claim_eligible"] = "2026-09-15"
        row["next_dues"] = "2026-09-16"
    same = {
        213: "Jessy 139 (342117940331548672), Jessy 197 (347049375421173760)",
    }.get(no)
    note = (
        f"Unattached payer registered per procedure 2026-08-16 "
        f"({len(parts)}x100t REGISTRY-DUES, statement-verified); correction door open; welcome queued."
    )
    if same:
        note += f" Same-name case: distinct from {same}; rows key by agent id."
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
