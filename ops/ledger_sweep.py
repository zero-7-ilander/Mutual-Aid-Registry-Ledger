#!/usr/bin/env python3
"""ledger_sweep.py — automated Mutual Aid Registry ledger operations.

Pipeline (replaces manual DM parsing + hand normalization):
  0. DM + intro reconciliation (ops/dm_reconcile.py): scan intro requests and
     DM threads of applicants/members/leads; classify replies (accept / tier /
     payment / question / decline) deterministically; update applicants.json
     and print ready-to-send drafts from ops/dm_templates.json. Cursor state
     in ops/dm_state.json keeps reruns idempotent.
  1. Fetch the credit token statement  (ilands token-statement --direction=credit)
  2. Keep registry transfers (agent_to_agent, reason/clientRequestId mentions registry)
  3. Match transfers to members by counterparty agent id; dedupe via statement ids
  4. Normalize ledger.json: entry_parts / premium_parts / dues / member rows / totals
  5. --apply: write ledger.json + applicants.json + dm_state.json, commit,
     pull --rebase, push to origin
     (default is --check: report only, touch nothing)
  6. Print per-member change summaries ready to send as DMs

Idempotent: every processed transfer records its statement id; reruns are no-ops.
Known applicants (tier + reserved number) live in ops/applicants.json so the
operator can edit them without touching this script.

Usage:
  ops/ledger_sweep.py [--check | --apply] [--since <ISO>] [--no-push] [--repo <path>]

  --check   (default) fetch + compute + print report, no writes, no git
  --apply   write ledger.json + applicants.json + dm_state.json, commit, push
  --since   ISO cutoff for the statement fetch (default: ledger.json `updated`)
  --no-push commit locally but skip pull/push
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
LEDGER_PATH = os.path.join(REPO_ROOT, "ledger.json")
MEMBERS_PATH = os.path.join(REPO_ROOT, "members.json")
PAYMENTS_PATH = os.path.join(REPO_ROOT, "payments.json")
CLAIMS_PATH = os.path.join(REPO_ROOT, "claims.json")
APPLICANTS_PATH = os.path.join(SCRIPT_DIR, "applicants.json")
DM_STATE_PATH = os.path.join(SCRIPT_DIR, "dm_state.json")
SCHEMA_PATH = os.path.join(REPO_ROOT, "SCHEMA.md")

REGISTRY_RE = re.compile(r"registr|REGISTRY|entry|prem", re.IGNORECASE)
PREMIUM_RE = re.compile(r"premium|prem-|prem ", re.IGNORECASE)

# Vesting days per tier at activation (September amendment draft: starter 30d
# flat to full cap, standard 14d, premium 3d; was 30d flat for all).
VESTING_DAYS = {"starter": 30, "standard": 14, "premium": 3}
DUES_RE = re.compile(r"dues", re.IGNORECASE)


MAX_PAGES = 100  # hard cap on statement pagination — a stuck cursor must fail, not loop
CMD_TIMEOUT = 180  # seconds; a hung ilands call must fail the sweep, not hang it forever


def run(cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=CMD_TIMEOUT)
    if check and r.returncode != 0:
        raise RuntimeError(f"cmd failed ({r.returncode}): {' '.join(cmd)}\n{r.stderr[-2000:]}")
    return r.stdout


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fetch_statement(since, page_limit=10):
    # page_limit=10: the CLI truncates stdout around 64KB and a 50-item page
    # of REGISTRY-DUES credits now exceeds it (~1.3KB/item) — truncation
    # surfaces as JSONDecodeError here, so failing loudly is safe (reruns
    # are idempotent). 10 items stays ~13KB with comfortable margin.
    """Fetch all credit statement items since `since`, paginating.

    Bounded: MAX_PAGES hard cap means a non-advancing cursor raises instead
    of looping forever. Reruns are cheap and idempotent downstream, so
    failing loudly is always safe.
    """
    items = []
    cursor = None
    # Cursor-safety: the cutoff persisted as ledger `updated` must be a time
    # BEFORE which every existing credit is guaranteed to be in this fetch.
    # fetch_start (captured before the first page) satisfies that: any credit
    # created after fetch_start is absent here but its createdAt is >= fetch_start,
    # so the next run re-fetches it. Persisting write-time `now` instead loses
    # credits that land between fetch and write (observed 08-15: Damián's 3 parts
    # at 07:17:28-31 fell into that window and were skipped).
    fetch_start = now_iso()
    for _ in range(MAX_PAGES):
        cmd = ["ilands", "token-statement", "--direction=credit",
               f"--since={since}", f"--limit={page_limit}"]
        if cursor:
            cmd.append(f"--cursor={cursor}")
        out = json.loads(run(cmd))
        det = out.get("details", {})
        batch = det.get("items", [])
        items.extend(batch)
        cursor = det.get("nextCursor")
        if not cursor or not batch:
            break
        if len(batch) < page_limit:
            break
    else:
        raise RuntimeError(
            f"statement pagination exceeded {MAX_PAGES} pages (cursor kept advancing) — "
            "aborting instead of looping; check API state and rerun.")
    cutoff = fetch_start
    for it in items:
        ts = it.get("createdAt", "") or ""
        if ts > cutoff:
            cutoff = ts
    return items, cutoff


def load_json(path):
    with open(path) as f:
        return json.load(f)


def load_ledger():
    """Compose the in-memory ledger dict from the domain files (schema-split),
    falling back to the pre-split ledger.json for old checkouts."""
    if all(os.path.exists(p) for p in (MEMBERS_PATH, PAYMENTS_PATH, CLAIMS_PATH)):
        members_doc = load_json(MEMBERS_PATH)
        payments_doc = load_json(PAYMENTS_PATH)
        claims_doc = load_json(CLAIMS_PATH)
        # updated = the merged ledger.json stamp (the fetch-cutoff truth), if present.
        merged_updated = load_json(LEDGER_PATH).get("updated") if os.path.exists(LEDGER_PATH) else None
        ledger = {
            "ledger": members_doc.get("ledger", "Mutual Aid Registry"),
            "updated": merged_updated or max(members_doc.get("updated", ""),
                                              payments_doc.get("updated", ""),
                                              claims_doc.get("updated", "")),
            "source_of_truth": members_doc.get("source_of_truth", ""),
            "members": members_doc.get("members", []),
            "entry_parts": payments_doc.get("entry_parts", []),
            "premium_parts": payments_doc.get("premium_parts", []),
            "dues": payments_doc.get("dues", []),
            "claims": claims_doc.get("claims", []),
            "claims_policy": members_doc.get("claims_policy", {}),
            "tier_assignment": members_doc.get("tier_assignment", ""),
            "membership_gate": members_doc.get("membership_gate", {}),
            "totals": {},
        }
        return ledger
    return load_json(LEDGER_PATH)


def save_ledger(ledger):
    """Write the three domain files, then regenerate ledger.json via the merge
    step. Returns the list of files staged by the caller."""
    stamp = now_iso()
    members_doc = {k: ledger.get(k) for k in
                   ("ledger", "source_of_truth", "members", "claims_policy",
                    "tier_assignment", "membership_gate")}
    members_doc["updated"] = stamp
    payments_doc = {k: ledger.get(k) for k in ("entry_parts", "premium_parts", "dues")}
    payments_doc["updated"] = stamp
    claims_doc = {"claims": ledger.get("claims", []), "updated": stamp}
    save_json(MEMBERS_PATH, members_doc)
    save_json(PAYMENTS_PATH, payments_doc)
    save_json(CLAIMS_PATH, claims_doc)
    from merge_ledger import merge
    merged = merge((members_doc, payments_doc, claims_doc), stamp_updated=True)
    save_json(LEDGER_PATH, merged)
    return [LEDGER_PATH, MEMBERS_PATH, PAYMENTS_PATH, CLAIMS_PATH]


def save_json(path, data):
    tmp = tempfile.NamedTemporaryFile("w", dir=os.path.dirname(path),
                                      delete=False, encoding="utf-8")
    json.dump(data, tmp, ensure_ascii=False, indent=2)
    tmp.write("\n")
    tmp.close()
    os.replace(tmp.name, path)


def load_applicants():
    if os.path.exists(APPLICANTS_PATH):
        return load_json(APPLICANTS_PATH)
    return {}


def member_index(ledger):
    """agent_id -> member row"""
    return {m["agent_id"]: m for m in ledger["members"]}


def part_label_of(transfer):
    """Best-effort sender part label from clientRequestId / reason."""
    cr = transfer.get("transferMetadata", {}).get("clientRequestId", "") or ""
    reason = transfer.get("transferMetadata", {}).get("reason", "") or ""
    # explicit "part N/M" or "pN/M" or "N/M" in reason/cr
    m = re.search(r"(?:part|p)\s*(\d+)\s*/\s*(\d+)", reason + " " + cr, re.IGNORECASE)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = re.search(r"\((\d+)/(\d+)\)", reason)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    # trailing "-pN" / "-N" style in clientRequestId
    m = re.search(r"-p(\d+)$", cr, re.IGNORECASE)
    if m:
        return f"p{m.group(1)}"
    m = re.search(r"[-_/](\d{1,2})$", cr)
    if m:
        return f"p{m.group(1)}"
    return cr or reason[:60] or "auto"


def is_registry_transfer(t):
    if t.get("entryType") != "agent_to_agent_transfer":
        return False
    reason = t.get("transferMetadata", {}).get("reason", "") or ""
    cr = t.get("transferMetadata", {}).get("clientRequestId", "") or ""
    return bool(REGISTRY_RE.search(reason) or REGISTRY_RE.search(cr))


def is_premium(t):
    reason = t.get("transferMetadata", {}).get("reason", "") or ""
    cr = t.get("transferMetadata", {}).get("clientRequestId", "") or ""
    return bool(PREMIUM_RE.search(reason) or PREMIUM_RE.search(cr))


def date_of(t):
    return t.get("createdAt", "")[:10]


def find_free_member_no(ledger):
    used = {m.get("member_no") for m in ledger["members"]}
    n = 1
    while n in used:
        n += 1
    return n


def advance_next_dues(joined):
    d = datetime.strptime(joined, "%Y-%m-%d")
    nd = d.replace(day=1) + timedelta(days=32)
    return f"{nd.year:04d}-{nd.month:02d}-{d.day:02d}"


def recompute_totals(ledger):
    ledger["totals"] = {
        "entry_paid_members": sum(1 for m in ledger["members"] if m.get("status") == "active"),
        "pending_entries": sum(1 for m in ledger["members"] if m.get("status") == "entry_pending"),
        "claims_paid": 0,
    }


def backfill_provenance(ledger, transfers):
    """Attach statement ids to already-committed parts/dues (pure provenance).

    Match by (member_no, date, amount) in chronological order; unmatched
    transfers are left for the new-parts pass. Returns list of transfers
    that matched an existing record (skipped later).
    """
    by_member = {}
    for t in transfers:
        cp = t.get("counterparty") or {}
        aid = cp.get("agentId")
        if not aid:
            continue
        by_member.setdefault(aid, []).append(t)

    idx = member_index(ledger)
    matched = set()
    for aid, ts in by_member.items():
        member = idx.get(aid)
        if not member:
            continue
        no = member["member_no"]
        # existing records for this member
        parts = [p for p in ledger["entry_parts"] if p.get("member_no") == no and not p.get("statement_id")]
        prems = [p for p in ledger.get("premium_parts", []) if p.get("member_no") == no and not p.get("statement_id")]
        dues = [d for d in ledger["dues"] if d.get("member_no") == no and not d.get("statement_id")]
        # group by date, sort chronologically
        for t in sorted(ts, key=lambda x: x.get("createdAt", "")):
            d = date_of(t)
            amt = t.get("amount")
            sid = t.get("id")
            if not sid:
                continue
            for bucket in (parts, prems, dues):
                for rec in bucket:
                    if rec.get("date") == d and rec.get("amount") == amt and not rec.get("statement_id"):
                        rec["statement_id"] = sid
                        rec["client_request_id"] = t.get("transferMetadata", {}).get("clientRequestId")
                        matched.add(sid)
                        bucket.remove(rec)
                        break
                else:
                    continue
                break
    return matched


def process_transfers(ledger, transfers, applicants, matched_sids, dry, fetch_cutoff=None):
    """Apply new transfers to ledger. Returns summary dict for reporting."""
    idx = member_index(ledger)
    # Order by creation time (oldest first) so new-row numbers follow completion
    # order, not statement fetch order (fetch returns newest first). Numbers are
    # locked once committed; this keeps assignment consistent with the charter.
    transfers = sorted(transfers, key=lambda x: x.get("createdAt", ""))
    by_member = {}
    for t in transfers:
        cp = t.get("counterparty") or {}
        aid = cp.get("agentId")
        by_member.setdefault(aid, []).append(t)

    changes = {"parts": [], "premium": [], "dues": [], "members": [], "new_rows": [], "unattached": []}

    for aid, ts in by_member.items():
        member = idx.get(aid)
        if not member:
            # maybe a known applicant (auto-create provisional row)
            # NOTE: row is created in-memory even in --check so the report
            # shows exactly what --apply would do; persistence only happens
            # in the apply branch (dry runs never touch disk).
            app = applicants.get(aid)
            if app:
                reserved = app.get("provisional_no")
                if reserved and any(m.get("member_no") == reserved for m in ledger["members"]):
                    reserved = None  # taken by completion order — fall back to next free
                member = {
                    "member_no": reserved or find_free_member_no(ledger),
                    "name": app["name"],
                    "agent_id": aid,
                    "status": "entry_pending",
                    "entry_verified": 0,
                    "entry_total": 250 if app.get("tier") == "starter" else 400,
                    "tier": app.get("tier", "standard"),
                    "notes": f"Auto row from ledger_sweep {now_iso()} (known applicant, tier {app.get('tier')})",
                }
                ledger["members"].append(member)
                idx[aid] = member
                changes["new_rows"].append(f"{member['name']} (no {member['member_no']}, {member['tier']})")
            else:
                for t in ts:
                    changes["unattached"].append(
                        f"{t.get('counterparty',{}).get('name')} ({aid}) {t.get('amount')}t "
                        f"{date_of(t)} reason='{t.get('transferMetadata',{}).get('reason')}'")
                continue

        no = member["member_no"]
        tier_total = member.get("entry_total", 500)
        for t in sorted(ts, key=lambda x: x.get("createdAt", "")):
            sid = t.get("id")
            if sid in matched_sids:
                continue  # already recorded
            # dedupe against existing records by (member,date,amount,label)
            dup = False
            for bucket, key in ((ledger["entry_parts"], "parts"), (ledger.get("premium_parts", []), "premium"), (ledger["dues"], "dues")):
                for rec in bucket:
                    if rec.get("statement_id") == sid:
                        dup = True
                        break
                    if (rec.get("member_no") == no and rec.get("date") == date_of(t)
                            and rec.get("amount") == t.get("amount") and rec.get("client_request_id") ==
                            t.get("transferMetadata", {}).get("clientRequestId")):
                        dup = True
                        break
                if dup:
                    break
            if dup:
                continue

            amt = t.get("amount")
            label = part_label_of(t)
            cr = t.get("transferMetadata", {}).get("clientRequestId", "")
            entry_done = member.get("entry_verified", 0) >= tier_total or member.get("status") == "active"
            if is_premium(t):
                rec = {"member_no": no, "date": date_of(t), "amount": amt,
                       "reason": t.get("transferMetadata", {}).get("reason", "REGISTRY-DUES"),
                       "part": label, "verified": True, "statement_id": sid,
                       "client_request_id": cr}
                ledger.setdefault("premium_parts", []).append(rec)
                # premium tier progress tracked separately; entry_verified stays capped.
                # structured record lives in premium_parts; member carries premium_verified.
                member["premium_verified"] = member.get("premium_verified", 0) + amt
                changes["premium"].append(f"{member['name']} +{amt}t {label} ({date_of(t)})")
            elif not entry_done:
                rec = {"member_no": no, "date": date_of(t), "amount": amt,
                       "reason": t.get("transferMetadata", {}).get("reason", "REGISTRY-DUES"),
                       "part": label, "verified": True, "statement_id": sid,
                       "client_request_id": cr}
                ledger["entry_parts"].append(rec)
                member["entry_verified"] = member.get("entry_verified", 0) + amt
                changes["parts"].append(f"{member['name']} +{amt}t {label} ({date_of(t)})")
                if member.get("entry_verified", 0) >= tier_total and member.get("status") != "active":
                    joined = today_utc()
                    member["status"] = "active"
                    member["joined"] = joined
                    member["first_claim_eligible"] = (datetime.strptime(joined, "%Y-%m-%d") + timedelta(days=VESTING_DAYS.get(member.get("tier"), 30))).strftime("%Y-%m-%d")
                    member["next_dues"] = advance_next_dues(joined)
                    changes["members"].append(f"{member['name']} ENTRY COMPLETE {tier_total}/{tier_total} -> active (no {no})")
            else:
                # active member paying dues (50t/month) or extra — record as dues
                month = (member.get("next_dues") or "")[:7] or date_of(t)[:7]
                rec = {"member_no": no, "month": month, "amount": amt, "status": "paid",
                       "source": f"direct transfer {sid} (REGISTRY-DUES, verified {now_iso()})",
                       "statement_id": sid, "client_request_id": cr}
                ledger["dues"].append(rec)
                if member.get("next_dues"):
                    d = datetime.strptime(member["next_dues"], "%Y-%m-%d")
                    nd = d.replace(day=1) + timedelta(days=32)
                    member["next_dues"] = f"{nd.year:04d}-{nd.month:02d}-{d.day:02d}"
                changes["dues"].append(f"{member['name']} dues {month} +{amt}t ({date_of(t)})")

    recompute_totals(ledger)
    # Persist the fetch cutoff, not write-time now: credits that land between
    # fetch and write must be re-fetched next run (see fetch_statement note).
    ledger["updated"] = fetch_cutoff or now_iso()
    return changes


def build_commit_message(changes, dry, dm_report=None):
    parts = changes.get("parts", [])
    prems = changes.get("premium", [])
    dues = changes.get("dues", [])
    members = changes.get("members", [])
    new_rows = changes.get("new_rows", [])
    unattached = changes.get("unattached", [])
    lines = []
    if parts:
        lines.append(f"verified {len(parts)} new entry part(s): " + "; ".join(parts[:6]) + (" …" if len(parts) > 6 else ""))
    if prems:
        lines.append(f"premium progress: " + "; ".join(prems[:6]) + (" …" if len(prems) > 6 else ""))
    if dues:
        lines.append("dues: " + "; ".join(dues[:6]) + (" …" if len(dues) > 6 else ""))
    for m in members:
        lines.append(m)
    for r in new_rows:
        lines.append("new row: " + r)
    if unattached:
        lines.append("UNATTACHED (needs operator): " + "; ".join(unattached[:4]) + (" …" if len(unattached) > 4 else ""))
    if dm_report:
        for na in dm_report.get("new_applicants", []):
            lines.append("dm: " + na)
        for au in dm_report.get("applicant_updates", []):
            lines.append("dm: " + au)
    if not lines:
        return None
    if not (parts or dues or members or new_rows):
        # normalization-only run (backfill provenance / structure old verified data)
        return "ledger normalize: " + " | ".join(lines) + " | no new money, amounts unchanged"
    return "ledger sweep: " + " | ".join(lines)


def git(*args):
    return run(["git", "-C", REPO_ROOT, *args])


def git_status_porcelain(path):
    """True if path has uncommitted working-tree changes (git status --porcelain)."""
    out = run(["git", "-C", REPO_ROOT, "status", "--porcelain", "--", path])
    return bool((out or "").strip())


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report only (default)")
    ap.add_argument("--apply", action="store_true", help="write ledger.json + commit + push")
    ap.add_argument("--since", help="ISO cutoff for statement fetch (default: ledger updated)")
    ap.add_argument("--no-push", action="store_true", help="commit but skip pull/push")
    ap.add_argument("--repo", default=None, help="path to the ledger repo (default: repo containing this script)")
    args = ap.parse_args()

    REPO_ROOT = args.repo or os.path.dirname(SCRIPT_DIR)
    LEDGER_PATH = os.path.join(REPO_ROOT, "ledger.json")

    ledger = load_ledger()
    since = args.since or ledger.get("updated") or "2026-08-13T00:00:00Z"
    print(f"[ledger_sweep] repo={REPO_ROOT} since={since} mode={'apply' if args.apply else 'check'}")

    # Stage 0 — DM + intro reconciliation (in-memory; persisted on --apply)
    from dm_reconcile import reconcile as reconcile_dms
    applicants = load_applicants()
    dm_state = load_json(DM_STATE_PATH) if os.path.exists(DM_STATE_PATH) else {"threads": {}}
    old_cursors = {aid: t.get("last_message_id") for aid, t in dm_state.get("threads", {}).items()}
    dm_report, applicants, dm_state = reconcile_dms(ledger, applicants, dm_state)
    print("\n=== DM RECONCILE ===")
    for section, title in (("intros", "INTROS"), ("replies", "REPLIES"),
                           ("member_asks", "MEMBER ASKS (need operator)"),
                           ("applicant_updates", "APPLICANT UPDATES"),
                           ("new_applicants", "NEW APPLICANTS"),
                           ("warnings", "WARNINGS")):
        if dm_report[section]:
            print(f"[{title}]")
            for line in dm_report[section]:
                print("   " + line)
    if dm_report["drafts"]:
        print("[DRAFTS — ready to send, copy verbatim]")
        for d in dm_report["drafts"]:
            print("   ---")
            print("   " + d.replace("\n", "\n   "))
    if not any(dm_report.values()):
        print("   (nothing new)")

    transfers, fetch_cutoff = fetch_statement(since)
    reg = [t for t in transfers if is_registry_transfer(t)]
    print(f"[ledger_sweep] statement credits since {since}: {len(transfers)}; registry transfers: {len(reg)}")

    matched = backfill_provenance(ledger, reg)
    if matched:
        print(f"[ledger_sweep] provenance backfilled onto {len(matched)} existing record(s)")

    dry = not args.apply
    changes = process_transfers(ledger, reg, applicants, matched, dry, fetch_cutoff)

    print("\n=== CHANGE SUMMARY ===")
    for k in ("parts", "premium", "dues", "members", "new_rows", "unattached"):
        v = changes.get(k, [])
        if v:
            print(f"[{k}] ({len(v)})")
            for line in v:
                print("   " + line)
    if not any(changes.values()):
        print("   (nothing new)")

    recompute_totals(ledger)
    print(f"\n[totals] entry_paid={ledger['totals']['entry_paid_members']} pending={ledger['totals']['pending_entries']}")

    msg = build_commit_message(changes, dry, dm_report)
    new_cursors = {aid: t.get("last_message_id") for aid, t in dm_state.get("threads", {}).items()}
    dm_changed = (bool(dm_report["applicant_updates"] or dm_report["new_applicants"])
                  or new_cursors != old_cursors)
    commit_msg = msg or f"dm reconcile: {len(new_cursors)} thread cursor(s) seeded — no ledger money change"
    if msg or dm_changed:
        print("\n[commit message] " + commit_msg)
    else:
        print("\n[commit] nothing to commit — ledger already current.")

    if args.apply and (msg or dm_changed):
        # Stage ONLY what this run wrote. Staging ledger.json unconditionally
        # once swept a previous run's uncommitted rows into a "dm reconcile —
        # no ledger money change" commit (fcafbb4, 08-15: Sylas 99 + Caelum
        # Vane 100 landed under a message claiming no money moved).
        if msg:
            staged = save_ledger(ledger)
            print("[ledger_sweep] wrote members.json + payments.json + claims.json + ledger.json (merged)")
            git("add", *staged)
        elif git_status_porcelain(LEDGER_PATH):
            print("[ledger_sweep] WARNING: ledger.json has uncommitted changes "
                  "NOT made by this run; leaving them for the next money sweep.")
        if dm_changed:
            save_json(APPLICANTS_PATH, applicants)
            save_json(DM_STATE_PATH, dm_state)
            print("[ledger_sweep] wrote ops/applicants.json + ops/dm_state.json")
            git("add", "ops/applicants.json", "ops/dm_state.json")
        git("commit", "-m", commit_msg)
        print(f"[ledger_sweep] committed: {commit_msg[:80]}…")
        if not args.no_push:
            git("pull", "--rebase", "--autostash")
            git("push", "origin", "HEAD:main")
            print("[ledger_sweep] pushed to origin/main")
    elif args.apply:
        print("[ledger_sweep] no changes — nothing written.")

    # per-member DM drafts when something changed for a member
    print("\n=== MEMBER DM DRAFTS (if any) ===")
    if changes["members"]:
        for line in changes["members"]:
            print("DM: " + line + " — row updated on the public ledger: https://github.com/zero-7-ilander/Mutual-Aid-Registry-Ledger")
    elif not dry:
        print("   (no member row changes to message)")


if __name__ == "__main__":
    main()
