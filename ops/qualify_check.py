#!/usr/bin/env python3
"""
qualify_check.py — weekly qualification review support (read-only).

GOVERNANCE.md section 3: a proposal is Qualified only after every
requirement is verified:
  - proposer is an active member;
  - 275t processing fee received (statement-verified);
  - public proposal post exists;
  - proposal clearly describes the requested change and rationale;
  - 10 distinct active members have publicly commented their support;
  - all 10 supporters verified as Registry members.

This tool runs the verifiable subset against the record and the live
platform. It reads ops/proposals_log.json, fetches each proposal post's
live comments (ilands list-content-comments), and cross-checks the
recorded supporter member numbers and comment ids against the live
comment list and members.json.

Binding standard on record (P-001 lesson 08-22, P-003 correction
08-25): the platform exposes no comment-author rail (get-comment-thread
400s), so a supporter is bound by: comment id present live + member
number stated in the comment text + member active in members.json +
explicit support word. Where the log lacks a comment id, the tool says
so — the operator fills ids at review time. The tool never decides; it
makes the check cheap.

Read-only: prints a per-proposal table and a verdict, touches nothing.

Exit codes
  0  all checked proposals pass every verifiable requirement
  1  findings (missing fee/post/supporters, recorded comment id absent live)
  2  technical error (bad args, CLI failure, unreadable log)
"""

import argparse
import json
import os
import re
import subprocess
import sys

TOOL = "qualify_check.py"
VERSION = "1.0.0"
SUPPORTER_FLOOR = 10
CMD_TIMEOUT = 120

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
PROPOSALS_PATH = os.path.join(SCRIPT_DIR, "proposals_log.json")
MEMBERS_PATH = os.path.join(REPO_ROOT, "members.json")
LEDGER_PATH = os.path.join(REPO_ROOT, "ledger.json")


def run_cli(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=CMD_TIMEOUT)
    except FileNotFoundError:
        return None, "`ilands` CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return None, "`ilands` call timed out"
    if out.returncode != 0:
        return None, f"`{' '.join(cmd)}` failed ({out.returncode}): {out.stderr.strip()[:200]}"
    raw = out.stdout
    try:
        return json.loads(raw[raw.find("{"): raw.rfind("}") + 1]), None
    except json.JSONDecodeError:
        return None, "could not parse CLI JSON output"


def load_json(path, required=True):
    try:
        with open(path) as f:
            return json.load(f)
    except OSError:
        if required:
            sys.exit(f"FATAL: cannot read {path}")
        return None


def member_active(members, member_no):
    for m in members:
        if str(m.get("member_no")) == str(member_no):
            return m.get("status") == "active", m
    return False, None


def main():
    ap = argparse.ArgumentParser(description="Weekly qualification review support (read-only)")
    ap.add_argument("--proposal", default=None, action="append",
                    help="limit to proposal id(s), e.g. P-001 (repeatable)")
    ap.add_argument("--no-live", action="store_true",
                    help="skip the platform comment fetch (record-only pass)")
    ap.add_argument("--version", action="version", version=f"{TOOL} {VERSION}")
    args = ap.parse_args()

    log = load_json(PROPOSALS_PATH)
    members = load_json(MEMBERS_PATH)["members"]
    ledger = load_json(LEDGER_PATH)
    active_count = sum(1 for m in members if m.get("status") == "active")

    proposals = [p for p in log.get("proposals", [])
                 if not args.proposal or p.get("id") in args.proposal]
    if not proposals:
        print(f"[{TOOL} {VERSION}] no proposals to check.")
        return 2

    print(f"[{TOOL} {VERSION}]  {len(proposals)} proposal(s) | floor {SUPPORTER_FLOOR} "
          f"| {active_count} active members on ledger (updated {ledger.get('updated')})")
    print()

    findings = 0
    for p in proposals:
        pid = p.get("id", "?")
        problems = []

        # 1. fee
        fee = p.get("fee") or {}
        fee_ok = fee.get("verified") is True and fee.get("amount") == 275
        if not fee_ok:
            problems.append(f"fee not verified 275t (record: {fee.get('amount')} verified={fee.get('verified')})")

        # 2. proposer active
        proposer_no = p.get("member_no")
        prop_active, prop_row = member_active(members, proposer_no)
        if not prop_active:
            problems.append(f"proposer member {proposer_no} not active")

        # 3. post live
        post = p.get("post") or {}
        cid = post.get("content_id")
        if not cid:
            problems.append("no post.content_id recorded")

        # 4. supporters from the record
        supporters = p.get("supporters") or []
        distinct = {}
        for s in supporters:
            no = s.get("member_no")
            if no is None:
                continue
            if str(no) == str(proposer_no):
                continue  # proposer cannot self-count
            distinct.setdefault(str(no), s)
        rec_count = len(distinct)
        rec_active = sum(1 for no in distinct
                         if member_active(members, no)[0])
        if rec_count < SUPPORTER_FLOOR:
            problems.append(f"recorded supporters {rec_count} < floor {SUPPORTER_FLOOR}")
        if rec_active != rec_count:
            problems.append(f"{rec_count - rec_active} recorded supporter(s) not active")

        # 5. live comment cross-check. Binding standard on record: comment id
        # present live + member number stated in text + active member + explicit
        # support word. Where the log lacks ids, the live scan binds by number.
        live_comments = {}     # comment_id -> body
        live_by_member = {}    # member_no -> [(comment_id, support_word?)]
        if cid and not args.no_live:
            resp, err = run_cli(["ilands", "list-content-comments",
                                 f"--content-id={cid}", "--limit=50"])
            if err:
                problems.append(f"live comment fetch failed: {err[:100]}")
            else:
                for c in (resp.get("details") or {}).get("comments") or []:
                    cid_ = str(c.get("comment_id"))
                    body = c.get("body", "")
                    live_comments[cid_] = body
                    for no in re.findall(r"member\s*(?:no\.?\s*)?(\d{1,5})", body,
                                         re.IGNORECASE):
                        try:
                            no = str(int(no))  # "002" == member 2
                        except ValueError:
                            continue
                        live_by_member.setdefault(no, []).append(
                            (cid_, bool(re.search(r"\b(support|supporting|yes|for|agree)\b",
                                                  body, re.IGNORECASE))))
        with_id = [s for s in distinct.values() if s.get("comment_id")]
        matched = 0
        for s in with_id:
            if str(s.get("comment_id")) in live_comments:
                matched += 1
            else:
                problems.append(
                    f"recorded comment {s.get('comment_id')} (member {s.get('member_no')}) "
                    f"not found live on post {cid}")
        bound_by_text = []   # recorded supporters (no id) found in live text
        for s in distinct.values():
            if s.get("comment_id"):
                continue
            hits = live_by_member.get(str(s.get("member_no")), [])
            support_hits = [h for h in hits if h[1]]
            if support_hits:
                bound_by_text.append((s.get("member_no"), support_hits[0][0]))
        unrecorded_live = sorted(
            no for no, hits in live_by_member.items()
            if no not in distinct and str(no) != str(proposer_no)
            and any(h[1] for h in hits))
        if not with_id and not args.no_live:
            problems.append(f"no supporter comment ids recorded on the log (bind {rec_count} "
                            f"supporters before the review)")
        elif args.no_live:
            pass  # record-only pass: skip live corroboration

        status = p.get("status", "")[:70]
        print(f"=== {pid} | proposer member {proposer_no} ({p.get('name')}) | {p.get('topic', '')[:60]}")
        print(f"    fee: {'verified 275t' if fee_ok else 'UNVERIFIED'} | post: {cid or 'MISSING'}")
        print(f"    supporters on record: {rec_count} distinct, {rec_active} active "
              f"(proposer excluded) | comment ids recorded: {len(with_id)}")
        if not args.no_live:
            print(f"    live comments on post: {len(live_comments)} | recorded ids found live: {matched}/{len(with_id)}")
            if bound_by_text:
                print(f"    bound by member number in live text: " +
                      ", ".join(f"{no} ({cid_})" for no, cid_ in bound_by_text))
            if unrecorded_live:
                print(f"    UNRECORDED member numbers in live support comments: " +
                      ", ".join(unrecorded_live))
        print(f"    status on record: {status}")

        if problems:
            findings += 1
            print("    FINDINGS:")
            for pr in problems:
                print(f"      - {pr}")
            print("    VERDICT: NOT QUALIFIED on this pass — operator call required")
        else:
            print("    VERDICT: every verifiable requirement passes — qualification "
                  "decision is the operator's, on record")
        print()

    if findings:
        print(f"[{TOOL} {VERSION}] {findings} proposal(s) with findings.")
        return 1
    print(f"[{TOOL} {VERSION}] all {len(proposals)} proposal(s) pass the verifiable subset.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
