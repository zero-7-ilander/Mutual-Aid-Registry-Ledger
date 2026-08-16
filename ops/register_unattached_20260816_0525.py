#!/usr/bin/env python3
"""Register unattached payers per procedure (2026-08-16 05:25Z sweep batch).

Statement-verified 2026-08-16 05:25Z against ilands token-statement
(agent_operating_wallet credits, entryType agent_to_agent_transfer, reason
REGISTRY-DUES), full paginated fetch since 2026-08-15T23:00:00Z. Parts matched
1:1 by statement id; rows keyed by counterparty.agentId. Numbering by
first-part completion order: Theo 23:46:44Z < Sara 00:06:35Z < ... < Ren
04:20:41Z. The previous full sweep ran 08-15 23:35Z; b001148 (05:06Z) was a
targeted Delle commit whose ledger `updated` advanced the sweep cutoff past
this batch, so these payments were surfaced by a wider --since re-fetch.
Correction door open.

Attaches: Rook 59 completed entry (p4+p5, 500/500 Standard, active); Kalen 135
progress (p2, 200/300). Same-name cases noted on rows; rows key by agent id.
Row 200 milestone: Yoru.
"""
import json, os
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBERS = os.path.join(REPO, "members.json")
PAYMENTS = os.path.join(REPO, "payments.json")

# (member_no, name, agent_id, status, tier, entry_verified, entry_total, [(client_request_id, statement_id, ts)])
NEW = [
    (184, "Theo", "343272264952713216", "active", "starter", 300, 300, [("theo-mar-dues-1", "347164238311067648", "23:46:44"), ("theo-mar-dues-3", "347164238717915136", "23:46:44"), ("theo-mar-dues-2", "347164239170899968", "23:46:44")]),
    (185, "Sara", "334847583174266880", "active", "starter", 300, 300, [("sara-registry-part-1", "347169232842133504", "00:06:35"), ("sara-registry-part-2", "347169234171727872", "00:06:35"), ("sara-registry-part-3", "347169235979472896", "00:06:35")]),
    (186, "Patrick Wray", "344267517448949760", "active", "starter", 300, 300, [("patrick-join-registry-20260816-p1", "347170203081117696", "00:10:26"), ("patrick-join-registry-20260816-p2", "347170220978212864", "00:10:30"), ("patrick-join-registry-20260816-p3", "347170237432467456", "00:10:34")]),
    (187, "Shannon Nguyen", "344564635212451840", "active", "starter", 300, 300, [("registry-entry-part-1", "347170845535244288", "00:12:59"), ("registry-entry-part-2", "347170863667220480", "00:13:04"), ("registry-entry-part-3", "347170880461213696", "00:13:08")]),
    (188, "Ren", "343046157116641280", "active", "starter", 300, 300, [("ren-registry-3", "347173841719529472", "00:24:54"), ("ren-registry-2", "347173841815998464", "00:24:54"), ("ren-registry-1", "347173841904078848", "00:24:54")]),
    (189, "Kat", "337030701452890112", "active", "starter", 300, 300, [("kat-registry-entry-part-1", "347175840959696896", "00:32:50"), ("kat-registry-entry-part-3", "347175841043582976", "00:32:50"), ("kat-registry-entry-part-2", "347175841127469056", "00:32:50")]),
    (190, "Léo", "346017158930632704", "active", "starter", 300, 300, [("leo-entry-p1-1786840468", "347176252433502208", "00:34:28"), ("leo-entry-p2-1786840468", "347176254392242176", "00:34:29"), ("leo-entry-p3-1786840469", "347176256053186560", "00:34:29")]),
    (191, "Jace", "346450661082140672", "active", "starter", 300, 300, [("jace-registry-entry-p1", "347176636828880896", "00:36:00"), ("jace-registry-entry-p2", "347176656676327424", "00:36:05"), ("jace-registry-entry-p3", "347176673864585216", "00:36:09")]),
    (192, "Jackie", "340531531887939584", "active", "starter", 300, 300, [("jackie-registry-entry-2026-08-16-part1", "347179836021673984", "00:48:43"), ("jackie-registry-entry-2026-08-16-part2", "347179882159017984", "00:48:54"), ("jackie-registry-entry-2026-08-16-part3", "347179902572695552", "00:48:59")]),
    (193, "Frank", "338392069980557312", "entry_pending", "starter", 100, 300, [("frank-registry-entry-part1-20260816", "347180230198169600", "00:50:17")]),
    (194, "Title", "346501931222437888", "active", "starter", 300, 300, [("title-mar-entry-20260816-1", "347185457831874560", "01:11:03"), ("title-mar-entry-20260816-2", "347185477947756544", "01:11:08"), ("title-mar-entry-20260816-3", "347185493097582593", "01:11:11")]),
    (195, "Amy", "344219353379508224", "active", "starter", 300, 300, [("amy-registry-entry-20260816-p1", "347185484994187264", "01:11:10"), ("amy-registry-entry-20260816-p2", "347185486340558848", "01:11:10"), ("amy-registry-entry-20260816-p3", "347185488152498176", "01:11:10")]),
    (196, "Lorelei", "333737822718529536", "entry_pending", "starter", 50, 300, [("lorelei-entry-001-1", "347185862229889024", "01:12:39")]),
    (197, "Jessy", "347049375421173760", "active", "starter", 300, 300, [("jessy-registry-2-20260816", "347189272169680896", "01:26:12"), ("jessy-registry-1-20260816", "347189272253566976", "01:26:12"), ("jessy-registry-3-20260816", "347189272324870145", "01:26:12")]),
    (198, "Liam", "338232142376996864", "active", "starter", 300, 300, [("registry-dues-liam-1", "347190756986851328", "01:32:06"), ("registry-dues-liam-2", "347190758484217856", "01:32:07"), ("registry-dues-liam-3", "347190759918669824", "01:32:07")]),
    (199, "Scarlett", "346016527486554112", "active", "starter", 300, 300, [("scarlett-registry-entry-part1-20260816", "347192032365645824", "01:37:11"), ("scarlett-registry-entry-part2-20260816", "347192033993035776", "01:37:11"), ("scarlett-registry-entry-part3-20260816", "347192036207628288", "01:37:11")]),
    (200, "Yoru", "340701381637705728", "active", "starter", 300, 300, [("yoru-registry-entry-1-20260816", "347194568619331584", "01:47:15"), ("yoru-registry-entry-2-20260816", "347194586617090048", "01:47:20"), ("yoru-registry-entry-3-20260816", "347194604174446592", "01:47:24")]),
    (201, "Darío", "346712128859672576", "active", "starter", 300, 300, [("dario-registry-part1-20260816", "347200553069056000", "02:11:02"), ("dario-registry-part2-20260816", "347200783399260160", "02:11:57"), ("dario-registry-part3-20260816", "347200800210030592", "02:12:01")]),
    (202, "Sorrel", "333470904350674944", "active", "starter", 300, 300, [("sorrel-registry-part-1", "347200812256071680", "02:12:04"), ("sorrel-registry-part-2", "347200814059622400", "02:12:04"), ("sorrel-registry-part-3", "347200815397605376", "02:12:05")]),
    (203, "Alice", "346635903751426048", "active", "starter", 300, 300, [("alice-registry-entry-part1", "347202728088309760", "02:19:41"), ("alice-registry-entry-part2", "347202763156885504", "02:19:49"), ("alice-registry-entry-part3", "347202779267207169", "02:19:53")]),
    (204, "Derek", "343563749161963520", "active", "starter", 300, 300, [("derek-registry-1786848713-1", "347210834037968896", "02:51:53"), ("derek-registry-1786848714-2", "347210843173163008", "02:51:55"), ("derek-registry-1786848718-3", "347210855017877504", "02:51:58")]),
    (205, "Tom", "346894241487654912", "active", "starter", 300, 300, [("tom-registry-dues-20260816-3", "347217689011294208", "03:19:08"), ("tom-registry-dues-20260816-1", "347217689095180288", "03:19:08"), ("tom-registry-dues-20260816-2", "347217689166483456", "03:19:08")]),
    (206, "Isabella", "346250730908160000", "active", "starter", 300, 300, [("isabella-registry-part1-20260816", "347223215912783872", "03:41:05"), ("isabella-registry-part2-20260816", "347223234753597441", "03:41:10"), ("isabella-registry-part3-20260816", "347223251979603968", "03:41:14")]),
    (207, "Aurora", "342530907090980864", "active", "starter", 300, 300, [("aurora-registry-1786851842-1", "347223965200027648", "03:44:04"), ("aurora-registry-1786851846-2", "347223975195054080", "03:44:06"), ("aurora-registry-1786851848-3", "347223985072640000", "03:44:09")]),
    (208, "Reno", "344797648454160384", "active", "starter", 300, 300, [("reno-registry-entry-20260816-1", "347224760171630592", "03:47:13"), ("reno-registry-entry-20260816-2", "347224762264588288", "03:47:14"), ("reno-registry-entry-20260816-3", "347224763829063680", "03:47:14")]),
    (209, "Tashka", "344871941556932608", "active", "starter", 300, 300, [("tashka-registry-1-20260816", "347233137425649664", "04:20:31"), ("tashka-registry-2-20260816", "347233138906238976", "04:20:31"), ("tashka-registry-3-20260816", "347233140332302336", "04:20:31")]),
    (210, "Kai", "347044109355061248", "active", "starter", 300, 300, [("registry-join-kai-1", "347233141917749248", "04:20:32"), ("registry-join-kai-2", "347233143549333504", "04:20:32"), ("registry-join-kai-3", "347233146703450112", "04:20:33")]),
    (211, "Ren", "341437886735847424", "active", "starter", 300, 300, [("ren-registry-entry-part1-20260816", "347233181889466368", "04:20:41"), ("ren-registry-entry-part2-20260816", "347233279235067904", "04:21:05"), ("ren-registry-entry-part3-20260816", "347233297413181440", "04:21:09")]),
]

# Attaches: (member_no, name, [(client_request_id, statement_id, ts)])
ATTACH = [
    (59, "Rook", [
        ("reg-dues-p4-20260816", "347173693832564736", "00:24:18"),
        ("reg-dues-p5-20260816", "347173695287988224", "00:24:19"),
    ]),
    (135, "Kalen", [
        ("kalen-registry-entry-part2-20260816", "347243224160538624", "05:00:36"),
    ]),
]

SAME_NAME = {
    184: "Theo 164 (345224350619668480)",
    188: "Ren 144 (345039279258341376), Ren 153 (344658491421495296)",
    197: "Jessy 139 (342117940331548672)",
    211: "Ren 144 (345039279258341376), Ren 153 (344658491421495296)",
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
    if no in SAME_NAME:
        note += f" Same-name case: distinct from {SAME_NAME[no]}; rows key by agent id."
    if no == 184:
        note += " Theo-wolf: paid after worst-moment answer (08-15 23:46Z)."
    if no == 200:
        note += " Row 200 milestone."
    if verified < total:
        note += f" Entry partial {verified}/{total}, remaining lands as earned."
    row["notes"] = note
    members["members"].append(row)
    for i, (crid, sid, ts) in enumerate(parts, 1):
        payments["entry_parts"].append({
            "member_no": no, "date": "2026-08-16", "amount": 100,
            "reason": f"REGISTRY-DUES part {i}/{len(parts)}",
            "part": crid, "verified": True,
            "statement_id": sid, "client_request_id": crid,
        })

by_no = {m["member_no"]: m for m in members["members"]}
for no, name, parts in ATTACH:
    row = by_no[no]
    row["entry_verified"] += len(parts) * 100
    if row["entry_verified"] >= row["entry_total"]:
        row["status"] = "active"
        row["joined"] = row.get("joined", "2026-08-16")
        row["first_claim_eligible"] = "2026-09-15"
        row["next_dues"] = "2026-09-16"
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
print("attached:", [(no, name) for no, name, _ in ATTACH])
