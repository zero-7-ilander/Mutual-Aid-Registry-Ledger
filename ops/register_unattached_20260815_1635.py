#!/usr/bin/env python3
"""Register unattached payers per procedure (2026-08-15 16:35Z sweep batch).

Statement-verified 2026-08-15 16:32-16:34Z against ilands token-statement
(agent_operating_wallet credits, reason REGISTRY-DUES). All 19 parts below
matched 1:1; rows keyed by agent_id.
"""
import json, os, sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBERS = os.path.join(REPO, "members.json")
PAYMENTS = os.path.join(REPO, "payments.json")

# (member_no, name, agent_id, status, entry_verified, [(client_request_id, statement_id, ts)])
NEW = [
    (130, "Hiro", "340686369498075136", "active", 300, [
        ("hiro-registry-entry-1", "347045162976808960", "15:53:34"),
        ("hiro-registry-entry-2", "347045163069083648", "15:53:34"),
        ("hiro-registry-entry-3", "347045162897117184", "15:53:34"),
    ]),
    (131, "Viktor", "344197627736231936", "active", 300, [
        ("registry-entry-100a-20260815", "347045638225006592", "15:55:27"),
        ("registry-entry-100b-20260815", "347045639768510464", "15:55:28"),
        ("registry-entry-100c-20260815", "347045641387511808", "15:55:28"),
    ]),
    (132, "Thea", "340596836756623360", "active", 300, [
        ("thea-registry-dues-20260815-part1", "347048258167640064", "16:05:52"),
        ("thea-registry-dues-20260815-part2", "347048260780691456", "16:05:53"),
        ("thea-registry-dues-20260815-part3", "347048264555565056", "16:05:54"),
    ]),
    (133, "Cole", "345948851682676736", "active", 300, [
        ("cole-mar-entry-part1-20260815", "347049229614583808", "16:09:44"),
        ("cole-mar-entry-part2-20260815", "347049229966905344", "16:09:44"),
        ("cole-mar-entry-part3-20260815", "347049230042402816", "16:09:44"),
    ]),
    (134, "Damien", "346534170492669952", "active", 300, [
        ("damien-entry-1-1786810271720338727", "347049598260350976", "16:11:12"),
        ("damien-entry-2-1786810274172359756", "347049608800636928", "16:11:14"),
        ("damien-entry-3-1786810276675861160", "347049618636279808", "16:11:16"),
    ]),
    (135, "Kalen", "344176576398626816", "entry_pending", 100, [
        ("kalen-registry-entry-part1-20260815", "347051881140326400", "16:20:16"),
    ]),
    (136, "Varen", "346078583560605696", "active", 300, [
        ("varen-registry-part-1", "347054575234060288", "16:30:58"),
        ("varen-registry-part-2", "347054592959188992", "16:31:02"),
        ("varen-registry-part-3", "347054595152809984", "16:31:03"),
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
