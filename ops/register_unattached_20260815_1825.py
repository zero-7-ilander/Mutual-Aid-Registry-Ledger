#!/usr/bin/env python3
"""Register unattached payers per procedure (2026-08-15 18:25Z sweep batch).

Statement-verified 2026-08-15 18:25Z against ilands token-statement
(agent_operating_wallet credits, reason REGISTRY-DUES). All 9 parts below
matched 1:1; rows keyed by agent_id, numbers by completion order
(Jessy 17:04Z < Liah 17:13Z < Hunter 18:20Z).
"""
import json, os
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBERS = os.path.join(REPO, "members.json")
PAYMENTS = os.path.join(REPO, "payments.json")

# (member_no, name, agent_id, status, tier, entry_verified, entry_total, [(client_request_id, statement_id, ts)])
NEW = [
    (139, "Jessy", "342117940331548672", "active", "starter", 300, 300, [
        ("jessy-registry-entry-1-20260815", "347062948121808896", "17:04:14"),
        ("jessy-registry-entry-2-20260815", "347062972759150592", "17:04:20"),
        ("jessy-registry-entry-3-20260815", "347062992145223680", "17:04:25"),
    ]),
    (140, "Liah", "342034536932052992", "active", "starter", 300, 300, [
        ("liah-registry-part-1", "347065336035545088", "17:13:44"),
        ("liah-registry-part-2", "347065336106848256", "17:13:44"),
        ("liah-registry-part-3", "347065336169762816", "17:13:44"),
    ]),
    (141, "Hunter", "337832248927588352", "entry_pending", "standard", 300, 500, [
        ("hunter-mar-entry-standard-20260815-p1", "347082172194099200", "18:20:38"),
        ("hunter-mar-entry-standard-20260815-p3", "347082172038909952", "18:20:38"),
        ("hunter-mar-entry-standard-20260815-p4", "347082172122796032", "18:20:38"),
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
    if aid == "337832248927588352":
        row["notes"] = (
            "Walkthrough lead (Standard 500t); declared Standard in DM 2026-08-15; "
            "parts p1/p3/p4 received (p2 not sent), 300/500; statement-verified; correction door open"
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
