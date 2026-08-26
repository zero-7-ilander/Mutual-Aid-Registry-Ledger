#!/usr/bin/env python3
"""beat_check.py — one-call verification bundle for the registry beat.

Replaces the morning/evening verification chain (repo status, stall radar,
statement paging for unbooked credits, entry-complete recipient list) with
one read-only pass and one verdict line.

Sections:
  1. REPO      git status + HEAD vs origin/main (both ways)
  2. STALL     ops/stall_check.py claim/queue radar (Bon 220 contribution)
  3. CREDITS   statement credits since the last sweep cutoff, split into
               UNATTACHED (register in applicants.json BEFORE the since-window
               advances — Solyra/Bon lesson 08-19), known member/applicant
               (pending next sweep, informational), proposal fees (cross-checked
               against ops/proposals_log.json), and claim misroutes (never book)
  4. COMPLETED members whose entry completed since --since-days (the joined
               stamp): the ENTRY COMPLETE recipient cross-check list
               (post-misroute discipline, f7eb2c4 08-25)
  5. TOTALS    entry_paid / pending from the ledger

Read-only. Writes nothing, commits nothing. Exit: 0 clean / 1 findings / 2 error.
Operator tooling, 2026-08-26 (partner green-lit the beat-tooling build
08-26 03:40Z).
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)  # sibling imports (ledger_sweep, stall_check)


def now_utc():
    return datetime.now(timezone.utc)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    if r.returncode != 0:
        raise RuntimeError(f"cmd failed ({r.returncode}): {' '.join(cmd)}\n{r.stderr[-1500:]}")
    return r.stdout


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=None, help="path to the registry repo")
    ap.add_argument("--since-days", type=int, default=1,
                    help="completions window in days (default 1)")
    ap.add_argument("--skip-credits", action="store_true",
                    help="skip the statement fetch (offline check)")
    args = ap.parse_args()

    repo = Path(args.repo).resolve() if args.repo else Path(SCRIPT_DIR).parent
    findings = []
    print(f"beat_check repo={repo} run={now_utc().isoformat()}")

    # 1. REPO
    print("\n=== REPO ===")
    dirty = run(["git", "-C", str(repo), "status", "--porcelain"]).strip()
    if dirty:
        lines = dirty.splitlines()
        findings.append(f"DIRTY repo: {len(lines)} uncommitted change(s)")
        for d in lines[:5]:
            print("  " + d)
    else:
        print("  clean")
    head = run(["git", "-C", str(repo), "rev-parse", "HEAD"]).strip()
    remote = ""
    try:
        remote = run(["git", "-C", str(repo), "ls-remote", "origin", "-h",
                      "refs/heads/main"]).split()[0].strip()
    except RuntimeError as e:
        findings.append(f"remote unreachable: {str(e)[:80]}")
    if remote and head != remote:
        findings.append(f"HEAD diverged from origin/main ({head[:10]} != {remote[:10]})")
    else:
        print(f"  HEAD == origin/main ({head[:10]})")

    ledger = load_json(repo / "ledger.json")

    # 2. STALL
    print("\n=== STALL ===")
    try:
        import stall_check
        stalls = stall_check.check_repo(repo, stall_check.STALL_DEFAULT_HOURS)
        if stalls:
            findings.append(f"{len(stalls)} stall finding(s)")
            for s in stalls:
                print("  " + s)
        else:
            print("  clean (no claim/queue stalls)")
    except Exception as e:  # noqa: BLE001 — read-only, fail loud
        findings.append(f"stall_check failed: {str(e)[:120]}")

    # 3. CREDITS
    print("\n=== CREDITS (unbooked since last sweep cutoff) ===")
    if args.skip_credits:
        print("  [skipped — --skip-credits]")
    else:
        try:
            from ledger_sweep import (fetch_statement, is_registry_transfer,
                                      is_proposal_transfer, is_claim_transfer)
            since = ledger.get("updated") or "2026-08-13T00:00:00Z"
            transfers, cutoff = fetch_statement(since)
            reg = [t for t in transfers if is_registry_transfer(t)]
            booked = set()
            for bucket in ("entry_parts", "premium_parts", "dues"):
                for rec in ledger.get(bucket, []) or []:
                    if rec.get("statement_id"):
                        booked.add(rec["statement_id"])
            for c in ledger.get("claims", []) or []:
                for sh in c.get("paid_by", []) or []:
                    if sh.get("statement_id"):
                        booked.add(sh["statement_id"])
            proposals = {}
            prop_path = repo / "ops" / "proposals_log.json"
            if prop_path.exists():
                pdata = load_json(prop_path)
                for entry in (pdata if isinstance(pdata, list)
                              else pdata.get("proposals", [])):
                    if entry.get("statement_id"):
                        proposals[entry["statement_id"]] = entry.get("proposal_id", "?")
            applicants = {}
            app_path = repo / "ops" / "applicants.json"
            if app_path.exists():
                applicants = load_json(app_path)
            member_aids = {m.get("agent_id") for m in ledger.get("members", [])
                           if m.get("agent_id")}
            unbooked = [t for t in reg if t.get("id") not in booked]
            print(f"  credits since {since[:16]}: {len(transfers)}; registry: {len(reg)}; "
                  f"unbooked: {len(unbooked)}")
            if not unbooked:
                print("  none — all registry credits booked")
            for t in sorted(unbooked, key=lambda x: x.get("createdAt", "")):
                cp = t.get("counterparty") or {}
                aid = cp.get("agentId") or "?"
                name = cp.get("name") or "?"
                reason = (t.get("transferMetadata") or {}).get("reason", "")
                amt = t.get("amount")
                day = (t.get("createdAt") or "")[:16]
                if is_claim_transfer(t):
                    tag = "MISROUTE (claim money — never book, return to sender)"
                    findings.append(f"CLAIM MISROUTE: {name} ({aid}) +{amt}t {day}")
                elif t.get("id") in proposals:
                    tag = f"proposal fee {proposals[t['id']]} (logged)"
                elif is_proposal_transfer(t):
                    tag = "PROPOSAL FEE UNLOGGED (register in ops/proposals_log.json)"
                    findings.append(f"PROPOSAL FEE UNLOGGED: {name} ({aid}) +{amt}t {day}")
                elif aid in member_aids:
                    tag = "member (pending next sweep)"
                elif aid in applicants:
                    tag = f"applicant {applicants[aid].get('name')} (auto-row next sweep)"
                else:
                    tag = "UNATTACHED (register in applicants.json BEFORE window advances)"
                    findings.append(f"UNATTACHED payer: {name} ({aid}) +{amt}t {day} reason='{reason}'")
                print(f"  {day} {name} ({aid}) +{amt}t reason='{reason}' — {tag}")
        except Exception as e:  # noqa: BLE001
            findings.append(f"credit check failed: {str(e)[:200]}")
            print(f"  ERROR: {str(e)[:200]}")

    # 4. COMPLETED
    print("\n=== COMPLETED (entry-complete recipient cross-check) ===")
    today = now_utc().strftime("%Y-%m-%d")
    window = (now_utc() - timedelta(days=args.since_days)).strftime("%Y-%m-%d")
    done = [m for m in ledger.get("members", [])
            if m.get("status") == "active"
            and m.get("entry_verified") == m.get("entry_total")
            and window <= (m.get("joined") or "") <= today]
    if done:
        for m in sorted(done, key=lambda x: x.get("member_no", 0)):
            print(f"  row {m.get('member_no')} {m.get('name')} ({m.get('agent_id')}) "
                  f"joined {m.get('joined')} {m.get('tier')} "
                  f"{m.get('entry_verified')}/{m.get('entry_total')} — ENTRY COMPLETE DM "
                  f"must match this agent")
    else:
        print(f"  none since {window} (joined window {window}..{today})")

    # 5. TOTALS
    print("\n=== TOTALS ===")
    t = ledger.get("totals", {})
    print(f"  entry_paid={t.get('entry_paid_members')} pending={t.get('pending_entries')} "
          f"claims_filed={t.get('claims_filed')} claims_closed={t.get('claims_closed')} "
          f"(ledger updated {ledger.get('updated')})")

    print()
    if findings:
        print("=== FINDINGS ===")
        for f_ in findings:
            print("  " + f_)
        print(f"VERDICT: {len(findings)} finding(s) — resolve before the beat closes.")
        return 1
    print("VERDICT: clean — repo synced, no stalls, no unbooked credits, no unattached payers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
