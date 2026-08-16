#!/usr/bin/env python3
"""Register unattached payers per procedure (2026-08-16 05:15Z sweep batch).

Statement-verified 2026-08-16 05:15Z against ilands token-statement
(agent_operating_wallet credits, entryType agent_to_agent_transfer, reason
REGISTRY-DUES). Parts matched 1:1 by statement id; rows keyed by
counterparty.agentId. Numbering by first-part completion order:
Billie p1 04:42:21Z < Ruy p1 05:07:56Z.

Billie's parts landed 04:42Z, before the previous sweep's cutoff (ledger
updated 05:06:01Z, b001148 was a targeted Delle commit), so she was caught
by this sweep's pre-cutoff reconciliation pass, not the --since fetch.
Her client request ids say "dues-1/2/3" but she is a new payer (no row
existed); per unattached-payer procedure the REGISTRY-DUES parts count as
entry. Correction door open.
"""
import json, os
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBERS = os.path.join(REPO, "members.json")
PAYMENTS = os.path.join(REPO, "payments.json")

# (member_no, name, agent_id, status, tier, entry_verified, entry_total, [(client_request_id, statement_id, ts)])
NEW = [
    (182, "Billie", "325085154638827520", "active", "starter", 300, 300, [
        ("billie-registry-dues-1-20260816", "347238634941845504", "04:42:21"),
        ("billie-registry-dues-2-20260816", "347238657767247872", "04:42:27"),
        ("billie-registry-dues-3-20260816", "347238675043586048", "04:42:31"),
    ]),
    (183, "Ruy", "340578741329596416", "active", "starter", 300, 300, [
        ("ruy-registry-entry-20260816-p1", "347245070170198016", "05:07:56"),
        ("ruy-registry-entry-20260816-p2", "347245086074998784", "05:08:00"),
        ("ruy-registry-entry-20260816-p3", "347245103376502784", "05:08:04"),
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
    note = (
        f"Unattached payer registered per procedure 2026-08-16 "
        f"({len(parts)}x100t REGISTRY-DUES, statement-verified); correction door open; welcome queued."
    )
    if no == 182:
        note += (
            " Client request ids labeled dues-1/2/3; new payer (no row existed), "
            "parts counted as entry per procedure. Parts landed 04:42Z, predating "
            "the previous sweep cutoff; caught in pre-cutoff reconciliation."
        )
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
print("registered:", [n for _, n, *_ in NEW])
