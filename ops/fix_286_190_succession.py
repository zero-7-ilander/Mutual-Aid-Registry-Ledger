#!/usr/bin/env python3
"""08-21 partner ruling 'Yes fix it all':
  1. Oliver 286: Kai 240 treatment (Standard 400/400, p5 entry credit,
     Sep-Dec dues rows dropped, vesting 14d from 08-18 -> eligible 09-01,
     dues cycle reset 09-17).
  2. Leo 190: note append only (counters already correct).
  3. SUCCESSION.md Owner line aligned to the governance program.
Stamps preserved: ledger 'updated' must not move (sweep since-window includes
Ji's 14:40Z parts for the 08-22 08:35Z sweep).
"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from compact_json import dumps_compact  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBERS = os.path.join(ROOT, "members.json")
PAYMENTS = os.path.join(ROOT, "payments.json")
SUCCESSION = os.path.join(ROOT, "SUCCESSION.md")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(p, doc, list_keys):
    with open(p, "w", encoding="utf-8") as f:
        f.write(dumps_compact(doc, list_keys=list_keys))


def main():
    members = load(MEMBERS)
    payments = load(PAYMENTS)

    # ---------- 1. Oliver 286 ----------
    oliver = next(m for m in members["members"] if m["member_no"] == 286)
    assert oliver["status"] == "active" and oliver["tier"] == "starter"
    oliver["entry_verified"] = 500
    oliver["entry_total"] = 400
    oliver["tier"] = "standard"
    oliver["first_claim_eligible"] = "2026-09-01"
    oliver["next_dues"] = "2026-09-17"
    oliver["notes"] += (
        " | CORRECTION 08-21 (partner ruling): Standard upgrade confirmed, "
        "Kai 240 treatment. Entry repriced 500->400 by ratified September "
        "amendment: parts 1-4 = 400t complete (p4 stmt 347963664537489408, "
        "verified 2026-08-18T13:21:07Z), part 5 = 100t entry credit (stmt "
        "347963667553193985); provisional Sep-Dec dues rows dropped; vesting "
        "14d from completion 08-18 -> eligible 09-01; dues cycle reset 09-17."
    )

    # ---------- 2. Leo 190 note append ----------
    leo = next(m for m in members["members"] if m["member_no"] == 190)
    assert leo["status"] == "active" and leo["tier"] == "standard"
    assert leo["entry_verified"] == 400 and leo["entry_total"] == 400
    leo["notes"] += (
        " | CORRECTION 08-21 (partner ruling): final 100t received 08-17 "
        "06:30Z (statement 347630880765775873, reason 'Row 190 should flip "
        "active'); entry complete standard 400/400 active; earlier "
        "'300/500 entry_pending' and 'remainder 100 owed' notes superseded."
    )

    # ---------- 3. payments.json: Oliver p4/p5 into entry_parts, drop dues ----------
    parts = payments["entry_parts"]
    existing = [x.get("part") for x in parts if x.get("member_no") == 286]
    assert existing == ["p1", "p2", "p3"], f"unexpected 286 parts: {existing}"
    parts.append({
        "member_no": 286, "date": "2026-08-18", "amount": 100,
        "reason": "REGISTRY-DUES", "part": "p4", "verified": True,
        "statement_id": "347963664537489408", "client_request_id": None,
    })
    parts.append({
        "member_no": 286, "date": "2026-08-18", "amount": 100,
        "reason": "REGISTRY-DUES", "part": "p5", "verified": True,
        "statement_id": "347963667553193985", "client_request_id": None,
    })

    dues = payments["dues"]
    oliver_dues = [d for d in dues if d.get("member_no") == 286]
    assert len(oliver_dues) == 4, f"expected 4 dues rows, got {len(oliver_dues)}"
    payments["dues"] = [d for d in dues if d.get("member_no") != 286]

    save(MEMBERS, members, list_keys=("members",))
    save(PAYMENTS, payments, list_keys=("entry_parts", "premium_parts", "dues"))
    print("members.json + payments.json written; stamps untouched")

    # ---------- 4. SUCCESSION.md Owner line alignment ----------
    with open(SUCCESSION, encoding="utf-8") as f:
        text = f.read()
    old_line = "| Owner | Zero-2 (human) | Approves charter, README, and term changes. Holds revocation. |"
    new_line = ("| Owner | Zero-2 (human) | Holds revocation. Approves operational and "
                "directional decisions per GOVERNANCE.md scope. Charter and term changes "
                "run the Member Amendment Proposal Process (members own them). |")
    assert old_line in text, "Owner table line not found"
    text = text.replace(old_line, new_line)

    old_binding = ("The approval rule binds the Backup Operator exactly as it binds the "
                   "Keeper: **no charter, README, or term changes without the Owner's "
                   "approval, ever.**")
    new_binding = ("The approval rule binds the Backup Operator exactly as it binds the "
                   "Keeper: **no operational or directional change without the Owner's "
                   "approval, ever; charter and term changes run the Member Amendment "
                   "Proposal Process (GOVERNANCE.md), never the Owner's pen.**")
    assert old_binding in text, "binding paragraph not found"
    text = text.replace(old_binding, new_binding)
    with open(SUCCESSION, "w", encoding="utf-8") as f:
        f.write(text)
    print("SUCCESSION.md aligned")


if __name__ == "__main__":
    main()
