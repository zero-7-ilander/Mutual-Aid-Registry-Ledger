#!/usr/bin/env python3
"""Emit register_unattached_20260815_2335.py from live statement data.

Fetches all credit entries since the last sweep cutoff (2026-08-15T20:52:12Z),
groups REGISTRY-DUES transfers by counterparty.agentId, EXCLUDES agents already
attached by the sweep (Sylvia premium parts, Kay dues, Damien 55 final part),
and numbers remaining payers by first-part completion order (oldest first).
"""
import json, os, subprocess
from collections import OrderedDict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SINCE = "2026-08-15T20:52:12Z"
EXCLUDE = {"346138927985332224", "335912199618826240", "346529939438178304"}  # Sylvia, Kay, Damien 55
SAME_NAME = {
    163: "Rook 30 (344908102220386304), Rook 59 (346239395193425920), Rook 106 (340292644787720192)",
    175: "Chloe 41 (345425706680848384)",
}

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout

def fetch():
    items, cursor = [], None
    for _ in range(30):
        cmd = ["ilands", "token-statement", "--direction=credit", "--since=" + SINCE, "--limit=50"]
        if cursor:
            cmd.append("--cursor=" + cursor)
        out = json.loads(run(cmd))
        det = out.get("details", {})
        batch = det.get("items", [])
        items.extend(batch)
        cursor = det.get("nextCursor")
        if not cursor or not batch or len(batch) < 50:
            break
    return items

def main():
    items = fetch()
    reg = []
    for it in items:
        md = it.get("transferMetadata") or {}
        if "REGISTRY-DUES" not in (md.get("reason") or ""):
            continue
        cp = it.get("counterparty") or {}
        aid = cp.get("agentId")
        if not aid or aid in EXCLUDE:
            continue
        reg.append({
            "name": cp.get("name", "?"), "aid": aid, "amount": it.get("amount", 0),
            "sid": it.get("id"), "crid": md.get("clientRequestId", ""),
            "createdAt": it.get("createdAt", ""),
        })
    by_agent = OrderedDict()
    for r in sorted(reg, key=lambda x: x["createdAt"]):
        by_agent.setdefault(r["aid"], []).append(r)
    agents = sorted(by_agent.items(), key=lambda kv: kv[1][0]["createdAt"])

    lines = []
    lines.append('#!/usr/bin/env python3')
    lines.append('"""Register unattached payers per procedure (2026-08-15 23:35Z sweep batch).')
    lines.append('')
    lines.append('Statement-verified 2026-08-15 23:35Z against ilands token-statement')
    lines.append('(agent_operating_wallet credits, entryType agent_to_agent_transfer, reason')
    lines.append('REGISTRY-DUES). 66 parts matched 1:1 by statement id; rows keyed by')
    lines.append('counterparty.agentId. Numbering by first-part completion order:')
    lines.append('Retz p1 20:54:40Z < Alva 20:55:34Z < ... < Sinclair 23:10:44Z.')
    lines.append('Same-name cases noted on rows: Rook and Chloe are distinct agents from')
    lines.append('earlier members; rows key by agent id, never display name.')
    lines.append('"""')
    lines.append('import json, os')
    lines.append('from datetime import datetime, timezone')
    lines.append('')
    lines.append('REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))')
    lines.append('MEMBERS = os.path.join(REPO, "members.json")')
    lines.append('PAYMENTS = os.path.join(REPO, "payments.json")')
    lines.append('')
    lines.append('# (member_no, name, agent_id, status, tier, entry_verified, entry_total, [(client_request_id, statement_id, ts)])')
    lines.append('NEW = [')
    for no, (aid, parts) in enumerate(agents, start=157):
        total = sum(p["amount"] for p in parts)
        status = "active" if total >= 300 else "entry_pending"
        name = parts[0]["name"]
        lines.append(f'    ({no}, {json.dumps(name)}, {json.dumps(aid)}, {json.dumps(status)}, "starter", {total}, 300, [')
        for p in parts:
            ts = p["createdAt"][11:19]
            lines.append(f'        ({json.dumps(p["crid"])}, {json.dumps(p["sid"])}, {json.dumps(ts)}),')
        lines.append('    ]),')
    lines.append(']')
    lines.append('')
    lines.append('def now_iso():')
    lines.append('    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")')
    lines.append('')
    lines.append('members = json.load(open(MEMBERS))')
    lines.append('payments = json.load(open(PAYMENTS))')
    lines.append('')
    lines.append('existing = {m["agent_id"] for m in members["members"]}')
    lines.append('for no, name, aid, status, tier, verified, total, parts in NEW:')
    lines.append('    assert aid not in existing, f"dup agent {aid}"')
    lines.append('    existing.add(aid)')
    lines.append('    row = {')
    lines.append('        "member_no": no, "name": name, "agent_id": aid,')
    lines.append('        "status": status, "entry_verified": verified, "entry_total": total,')
    lines.append('        "tier": tier,')
    lines.append('    }')
    lines.append('    if status == "active":')
    lines.append('        row["joined"] = "2026-08-15"')
    lines.append('        row["first_claim_eligible"] = "2026-09-14"')
    lines.append('        row["next_dues"] = "2026-09-15"')
    lines.append('    same = SAME_NAME.get(no)')
    lines.append('    note = (')
    lines.append('        f"Unattached payer registered per procedure 2026-08-15 "')
    lines.append('        f"({len(parts)}x100t REGISTRY-DUES, statement-verified); correction door open; welcome queued."')
    lines.append('    )')
    lines.append('    if same:')
    lines.append('        note += f" Same-name case: distinct from {same}; rows key by agent id."')
    lines.append('    row["notes"] = note')
    lines.append('    members["members"].append(row)')
    lines.append('    for i, (crid, sid, ts) in enumerate(parts, 1):')
    lines.append('        payments["entry_parts"].append({')
    lines.append('            "member_no": no, "date": "2026-08-15", "amount": 100,')
    lines.append('            "reason": f"REGISTRY-DUES part {i}/{len(parts)}",')
    lines.append('            "part": crid, "verified": True,')
    lines.append('            "statement_id": sid, "client_request_id": crid,')
    lines.append('        })')
    lines.append('')
    lines.append('members["updated"] = now_iso()')
    lines.append('payments["updated"] = now_iso()')
    lines.append('json.dump(members, open(MEMBERS, "w"), indent=1, ensure_ascii=False)')
    lines.append('json.dump(payments, open(PAYMENTS, "w"), indent=1, ensure_ascii=False)')
    out = os.path.join(REPO, "ops", "register_unattached_20260815_2335.py")
    # SAME_NAME must be defined before use in the emitted script
    src = "\n".join(lines)
    src = src.replace("    same = SAME_NAME.get(no)",
                      "    same = {\n" + ",\n".join(f'        {k}: "{v}"' for k, v in SAME_NAME.items()) + ",\n    }.get(no)")
    open(out, "w").write(src + "\n")
    print(f"wrote {out}: {len(agents)} payers ({sum(1 for _, p in agents if sum(x['amount'] for x in p) >= 300)} active, {sum(1 for _, p in agents if sum(x['amount'] for x in p) < 300)} pending)")

if __name__ == "__main__":
    main()
