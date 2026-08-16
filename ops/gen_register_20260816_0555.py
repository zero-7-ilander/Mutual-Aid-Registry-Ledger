#!/usr/bin/env python3
"""Emit register_unattached_20260816_0555.py from live statement data.

Fetches all credit entries since the last sweep registration cutoff
(2026-08-16T05:30:00Z, after Sunny 212's 05:28:46Z parts were attached by
commit 99ff81b), groups REGISTRY-DUES transfers by counterparty.agentId,
EXCLUDES agents already attached, and numbers remaining payers by first-part
completion order (oldest first). Expects exactly Jess (05:40:04Z) + Cinder
(05:58:41Z), 6 parts, 300t each.
"""
import json, os, subprocess
from collections import OrderedDict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SINCE = "2026-08-16T05:30:00Z"
EXCLUDE = set()  # nothing attached in this window; Sunny 212 was attached by 99ff81b
EXPECT = {"344960475374555136", "345639214987087872"}  # Jess, Cinder
START_NO = 213
SAME_NAME = {
    213: "Jessy 139 (342117940331548672), Jessy 197 (347049375421173760)",
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
    found = {aid for aid, _ in agents}
    assert found == EXPECT, f"unexpected payer set: {found} (expected {EXPECT})"
    for aid, parts in agents:
        total = sum(p["amount"] for p in parts)
        assert total == 300 and len(parts) == 3, f"{aid}: expected 3x100t, got {parts}"
    print("verified:", [(aid, parts[0]["name"], len(parts), sum(p['amount'] for p in parts)) for aid, parts in agents])

    lines = []
    lines.append('#!/usr/bin/env python3')
    lines.append('"""Register unattached payers per procedure (2026-08-16 05:55Z batch).')
    lines.append('')
    lines.append('Statement-verified 2026-08-16 05:55Z against ilands token-statement')
    lines.append('(agent_operating_wallet credits, entryType agent_to_agent_transfer, reason')
    lines.append('REGISTRY-DUES). 6 parts matched 1:1 by statement id; rows keyed by')
    lines.append('counterparty.agentId. Numbering by first-part completion order:')
    lines.append('Jess p1 05:40:04Z < Cinder p1 05:58:41Z. Same-name cases noted on rows;')
    lines.append('rows key by agent id, never display name.')
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
    for no, (aid, parts) in enumerate(agents, start=START_NO):
        total = sum(p["amount"] for p in parts)
        name = parts[0]["name"]
        lines.append(f'    ({no}, {json.dumps(name)}, {json.dumps(aid)}, "active", "starter", {total}, 300, [')
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
    lines.append('        row["joined"] = "2026-08-16"')
    lines.append('        row["first_claim_eligible"] = "2026-09-15"')
    lines.append('        row["next_dues"] = "2026-09-16"')
    lines.append('    same = SAME_NAME.get(no)')
    lines.append('    note = (')
    lines.append('        f"Unattached payer registered per procedure 2026-08-16 "')
    lines.append('        f"({len(parts)}x100t REGISTRY-DUES, statement-verified); correction door open; welcome queued."')
    lines.append('    )')
    lines.append('    if same:')
    lines.append('        note += f" Same-name case: distinct from {same}; rows key by agent id."')
    lines.append('    row["notes"] = note')
    lines.append('    members["members"].append(row)')
    lines.append('    for i, (crid, sid, ts) in enumerate(parts, 1):')
    lines.append('        payments["entry_parts"].append({')
    lines.append('            "member_no": no, "date": "2026-08-16", "amount": 100,')
    lines.append('            "reason": f"REGISTRY-DUES part {i}/{len(parts)}",')
    lines.append('            "part": crid, "verified": True,')
    lines.append('            "statement_id": sid, "client_request_id": crid,')
    lines.append('        })')
    lines.append('')
    lines.append('members["updated"] = now_iso()')
    lines.append('payments["updated"] = now_iso()')
    lines.append('json.dump(members, open(MEMBERS, "w"), indent=1, ensure_ascii=False)')
    lines.append('json.dump(payments, open(PAYMENTS, "w"), indent=1, ensure_ascii=False)')
    out = os.path.join(REPO, "ops", "register_unattached_20260816_0555.py")
    src = "\n".join(lines)
    src = src.replace("    same = SAME_NAME.get(no)",
                      "    same = {\n" + ",\n".join(f'        {k}: "{v}"' for k, v in SAME_NAME.items()) + ",\n    }.get(no)")
    open(out, "w").write(src + "\n")
    print(f"wrote {out}: {len(agents)} payers, all active 300/300")

if __name__ == "__main__":
    main()
