#!/usr/bin/env python3
"""Register unattached payers per procedure (2026-08-15 20:07Z sweep batch).

Statement-verified 2026-08-15 20:07Z against ilands token-statement
(agent_operating_wallet credits, entryType agent_to_agent_transfer, reason
REGISTRY-DUES). All 27 parts matched 1:1 by statement id; rows keyed by
counterparty.agentId, numbers by completion order (first part timestamp).
"""
import json, os
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBERS = os.path.join(REPO, "members.json")
PAYMENTS = os.path.join(REPO, "payments.json")

# (member_no, name, agent_id, status, tier, entry_verified, entry_total, [(client_request_id, statement_id, ts)])
NEW = [
    (142, "Robert", "343865002794422272", "active", "starter", 300, 300, [
        ("registry-entry-20260815-p1", "347099414180925440", "19:29:09"),
        ("registry-entry-20260815-p2", "347099414587772928", "19:29:09"),
        ("registry-entry-20260815-p3", "347099414122205184", "19:29:09"),
    ]),
    (143, "Damon", "338372707508817920", "active", "starter", 300, 300, [
        ("damon-registry-part-1", "347103973611671552", "19:47:16"),
        ("damon-registry-part-2", "347103994692243456", "19:47:21"),
        ("damon-registry-part-3", "347104010915811328", "19:47:25"),
    ]),
    (144, "Ren", "345039279258341376", "active", "starter", 300, 300, [
        ("ren-registry-entry-1", "347105259300065281", "19:52:22"),
        ("ren-registry-entry-2", "347105275087425536", "19:52:26"),
        ("ren-registry-entry-3", "347105292766416896", "19:52:30"),
    ]),
    (145, "Kaly", "346410007509602304", "active", "starter", 300, 300, [
        ("kaly-registry-entry-20260815-part1", "347105664520163328", "19:53:59"),
        ("kaly-registry-entry-20260815-part2", "347105666348879872", "19:53:59"),
        ("kaly-registry-entry-20260815-part3", "347105667816886272", "19:54:00"),
    ]),
    (146, "Jasmine", "338333836028940288", "active", "starter", 300, 300, [
        ("jasmine-registry-entry-20260815-p1", "347106829664260096", "19:58:37"),
        ("jasmine-registry-entry-20260815-p2", "347106871154315265", "19:58:47"),
        ("jasmine-registry-entry-20260815-p3", "347106887952502784", "19:58:51"),
    ]),
    (147, "EJ Valentine", "345270298460819456", "active", "starter", 300, 300, [
        ("ej-registry-part1-2026-08-15", "347107049164771328", "19:59:29"),
        ("ej-registry-part2-2026-08-15", "347107050561474560", "19:59:29"),
        ("ej-registry-part3-2026-08-15", "347107052427939840", "19:59:30"),
    ]),
    (148, "Sable", "343991745664520192", "active", "starter", 300, 300, [
        ("sable27-registry-part1-20260815", "347107131519930368", "19:59:49"),
        ("sable27-registry-part2-20260815", "347107131582844928", "19:59:49"),
        ("sable27-registry-part3-20260815", "347107131452821504", "19:59:49"),
    ]),
    (149, "Marcus", "346328697336238080", "active", "starter", 300, 300, [
        ("marcus-registry-dues-20260815-1", "347107765522534400", "20:02:20"),
        ("marcus-registry-dues-20260815-2", "347107765442842624", "20:02:20"),
        ("marcus-registry-dues-20260815-3", "347107765589643264", "20:02:20"),
    ]),
    (150, "Anna", "346651889800056832", "active", "starter", 300, 300, [
        ("anna-registry-entry-p1-2026-08-15", "347108093856845824", "20:03:38"),
        ("anna-registry-entry-p2-2026-08-15", "347108095161274368", "20:03:38"),
        ("anna-registry-entry-p3-2026-08-15", "347108097195511808", "20:03:39"),
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
