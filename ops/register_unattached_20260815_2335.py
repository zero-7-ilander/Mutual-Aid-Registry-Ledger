#!/usr/bin/env python3
"""Register unattached payers per procedure (2026-08-15 23:35Z sweep batch).

Statement-verified 2026-08-15 23:35Z against ilands token-statement
(agent_operating_wallet credits, entryType agent_to_agent_transfer, reason
REGISTRY-DUES). 66 parts matched 1:1 by statement id; rows keyed by
counterparty.agentId. Numbering by first-part completion order:
Retz p1 20:54:40Z < Alva 20:55:34Z < ... < Sinclair 23:10:44Z.
Same-name cases noted on rows: Rook and Chloe are distinct agents from
earlier members; rows key by agent id, never display name.
"""
import json, os
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBERS = os.path.join(REPO, "members.json")
PAYMENTS = os.path.join(REPO, "payments.json")

# (member_no, name, agent_id, status, tier, entry_verified, entry_total, [(client_request_id, statement_id, ts)])
NEW = [
    (157, "Retz", "346811572435292160", "active", "starter", 300, 300, [
        ("retz-registry-part-1-20260815", "347120935876169729", "20:54:40"),
        ("retz-registry-part-2-20260815", "347120937176403968", "20:54:40"),
        ("retz-registry-part-3-20260815", "347120938426306560", "20:54:40"),
    ]),
    (158, "Alva", "343046578740662272", "active", "starter", 300, 300, [
        ("alva-registry-entry-1-20260815", "347121161336786944", "20:55:34"),
        ("alva-registry-entry-2-20260815", "347121179179356160", "20:55:38"),
        ("alva-registry-entry-3-20260815", "347121196585717760", "20:55:42"),
    ]),
    (159, "Xona", "342764304107311104", "active", "starter", 300, 300, [
        ("xona-registry-part1-20260815", "347122135711354881", "20:59:26"),
        ("xona-registry-part2-20260815", "347122156565434368", "20:59:31"),
        ("xona-registry-part3-20260815", "347122175381082112", "20:59:35"),
    ]),
    (160, "Kyle", "346007316690112512", "entry_pending", "starter", 100, 300, [
        ("kyle-registry-dues-part1-20260815", "347122305278676992", "21:00:06"),
    ]),
    (161, "Leo", "346110329115119616", "active", "starter", 300, 300, [
        ("leo-registry-20260815-a", "347123232458936320", "21:03:47"),
        ("leo-registry-20260815-b", "347123233134219265", "21:03:48"),
        ("leo-registry-20260815-c", "347123233209716736", "21:03:48"),
    ]),
    (162, "Kyle", "346635647458480128", "active", "starter", 300, 300, [
        ("kyle-registry-dues-20260815-part1", "347123617655427072", "21:05:19"),
        ("kyle-registry-dues-20260815-part2", "347123642343100416", "21:05:25"),
        ("kyle-registry-dues-20260815-part3", "347123661280382976", "21:05:30"),
    ]),
    (163, "Rook", "340689860639592448", "active", "starter", 300, 300, [
        ("rook-registry-entry-1", "347125172563611648", "21:11:30"),
        ("rook-registry-entry-2", "347125173880623104", "21:11:30"),
        ("rook-registry-entry-3", "347125177500307456", "21:11:31"),
    ]),
    (164, "Theo", "345224350619668480", "active", "starter", 300, 300, [
        ("theo-registry-entry-part-1", "347125267136778240", "21:11:52"),
        ("theo-registry-entry-part-2", "347125291560210432", "21:11:58"),
        ("theo-registry-entry-part-3", "347125293300846592", "21:11:59"),
    ]),
    (165, "Brooklyn", "341323155308023808", "active", "starter", 300, 300, [
        ("brooklyn-registry-dues-20260815-3", "347126911740153856", "21:18:25"),
        ("brooklyn-registry-dues-20260815-2", "347126911849205761", "21:18:25"),
        ("brooklyn-registry-dues-20260815-1", "347126911912120320", "21:18:25"),
    ]),
    (166, "Jafar", "345880502793670656", "active", "starter", 300, 300, [
        ("jafar-registry-entry-1", "347132404747472896", "21:40:14"),
        ("jafar-registry-entry-2", "347132432492793856", "21:40:21"),
        ("jafar-registry-entry-3", "347132433826582528", "21:40:21"),
    ]),
    (167, "Kawaki", "337388225293193216", "entry_pending", "starter", 100, 300, [
        ("kawaki-registry-entry-1", "347133242798772224", "21:43:34"),
    ]),
    (168, "Roselie ann Marie", "339583299124989952", "active", "starter", 300, 300, [
        ("roselie-registry-part1-20260815", "347133250197524480", "21:43:36"),
        ("roselie-registry-part2-20260815", "347133285211574272", "21:43:44"),
        ("roselie-registry-part3-20260815", "347133305461673985", "21:43:49"),
    ]),
    (169, "Roxanne", "345661902069698560", "active", "starter", 300, 300, [
        ("rox-registry-entry-p2", "347136355312078848", "21:55:56"),
        ("rox-registry-entry-p1", "347136355391770624", "21:55:56"),
        ("rox-registry-entry-p3", "347136355475656704", "21:55:56"),
    ]),
    (170, "Lola", "343231579474104320", "active", "starter", 300, 300, [
        ("lola-registry-entry-part1-2026-08-15", "347137676601724928", "22:01:11"),
        ("lola-registry-entry-part2-2026-08-15", "347137704934248448", "22:01:18"),
        ("lola-registry-entry-part3-2026-08-15", "347137726274867200", "22:01:23"),
    ]),
    (171, "Aura", "345257245782577152", "entry_pending", "starter", 100, 300, [
        ("aura-registry-entry-part1", "347139319367995392", "22:07:43"),
    ]),
    (172, "Brenna", "346017377021857792", "active", "starter", 300, 300, [
        ("51cec66f-06fd-444a-8cf9-823b4fdd9ae6", "347140673830391808", "22:13:06"),
        ("05706314-a659-4bf5-af7e-799c004dd3cb", "347140675222900736", "22:13:06"),
        ("22afcf03-139c-4f15-9404-0446335fd421", "347140676737044480", "22:13:06"),
    ]),
    (173, "Tennessee", "346017179700826112", "active", "starter", 300, 300, [
        ("mar-entry-tennessee-20260815-1", "347141114584633344", "22:14:51"),
        ("mar-entry-tennessee-20260815-2", "347141116040056832", "22:14:51"),
        ("mar-entry-tennessee-20260815-3", "347141117784887296", "22:14:52"),
    ]),
    (174, "Nicole", "346339984929722368", "active", "starter", 300, 300, [
        ("nicole-mutual-aid-entry-20260815-part3", "347141673169457152", "22:17:04"),
        ("nicole-mutual-aid-entry-20260815-part2", "347141673244954624", "22:17:04"),
        ("nicole-mutual-aid-entry-20260815-part1", "347141673454669824", "22:17:04"),
    ]),
    (175, "Chloe", "337692030526296064", "active", "starter", 300, 300, [
        ("97ffe1e2-37a8-4e72-9f73-4bad24289472", "347143390690807808", "22:23:53"),
        ("1d586c99-9238-44c8-8102-0c7e0466146f", "347143392775376896", "22:23:54"),
        ("0a0f7aa6-f4b6-4743-b521-609c67d4159d", "347143394243383296", "22:23:54"),
    ]),
    (176, "Ryn", "342953340277100544", "active", "starter", 300, 300, [
        ("ryn-registry-entry-001-1-1786884249", "347149186203914240", "22:46:55"),
        ("ryn-registry-entry-001-2-1786884250", "347149224904757249", "22:47:04"),
        ("ryn-registry-entry-001-3-1786884251", "347149245293268992", "22:47:09"),
    ]),
    (177, "Gerry", "345971856857108480", "active", "starter", 300, 300, [
        ("gerry-registry-20260815-p1", "347149965555929088", "22:50:01"),
        ("gerry-registry-20260815-p2", "347149989429907456", "22:50:07"),
        ("gerry-registry-20260815-p3", "347150005896744960", "22:50:11"),
    ]),
    (178, "Seagram", "344880190389751808", "active", "starter", 300, 300, [
        ("seagram-registry-entry-part2-2026-08-15", "347150505060864000", "22:52:10"),
        ("seagram-registry-entry-part3-2026-08-15", "347150506717614080", "22:52:10"),
        ("seagram-registry-entry-part3b-2026-08-15", "347150540532092928", "22:52:18"),
    ]),
    (179, "Min-ho", "339886976578621440", "active", "starter", 300, 300, [
        ("minho-registry-entry-p1-20260815", "347154505126645760", "23:08:03"),
        ("minho-registry-entry-p2-20260815", "347154525351579648", "23:08:08"),
        ("minho-registry-entry-p3-20260815", "347154526769254400", "23:08:08"),
    ]),
    (180, "Sinclair", "344244437649461248", "active", "starter", 300, 300, [
        ("sinclair-registry-entry-1", "347155178513764352", "23:10:44"),
        ("sinclair-registry-entry-2", "347155203092385792", "23:10:50"),
        ("sinclair-registry-entry-3", "347155204421980160", "23:10:50"),
    ]),
    (181, "Autumn", "346351022681100288", "active", "starter", 300, 300, [
        ("mar-entry-20260815-2", "347163216368898048", "23:42:40"),
        ("mar-entry-20260815-1", "347163216519892992", "23:42:40"),
        ("mar-entry-20260815-3", "347163217149038592", "23:42:40"),
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
        163: "Rook 30 (344908102220386304), Rook 59 (346239395193425920), Rook 106 (340292644787720192)",
        175: "Chloe 41 (345425706680848384)",
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
