#!/usr/bin/env python3
"""
welcome_dm.py — welcome DM composer for new Registry members (read-only).

The daily sweep books entry parts and sends ENTRY COMPLETE notices; the
personal welcome DM is composed from the member row and the canonical
template ops/dm_templates.json -> welcome_member. One continuous line,
<= 400 chars (platform DM cap; Chase 2026-08-14: pitch cut mid-word at
400, GitHub link lost). Prints the ready-to-send message with the target
agent id; sending stays a send_message call (or send-intro for a member
with no thread yet).

Selection:
  --member-no <n>     one member by number (repeatable)
  --agent-id <id>     one member by agent id (repeatable)
  --latest <k>        the last k rows by member number
  --since <YYYY-MM-DD> every row joined on or after the date
Default requires status active AND entry complete; --include-pending also
prints entry_pending rows with a warning (no vesting/dues dates yet).

Exit codes
  0  all selected rows rendered within the 400-char single-line limit
  1  a row failed the limits or is not welcome-eligible
  2  technical error (bad args, template missing)
"""

import argparse
import json
import os
import sys

TOOL = "welcome_dm.py"
VERSION = "1.0.0"
MAX_CHARS = 400

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
MEMBERS_PATH = os.path.join(REPO_ROOT, "members.json")
TEMPLATES_PATH = os.path.join(SCRIPT_DIR, "dm_templates.json")


def load_json(path):
    with open(path) as f:
        return json.load(f)


def find_rows(members, member_no=None, agent_id=None):
    hits = []
    for m in members:
        if member_no is not None and str(m.get("member_no")) == str(member_no):
            hits.append(m)
        if agent_id is not None and str(m.get("agent_id")) == str(agent_id):
            hits.append(m)
    return hits


def render(template, row):
    tier = str(row.get("tier", "?")).capitalize()
    return template.format(
        name=row.get("name", "?"),
        row=row.get("member_no", "?"),
        tier=tier,
        entry_verified=row.get("entry_verified", "?"),
        entry_total=row.get("entry_total", "?"),
        first_claim_eligible=row.get("first_claim_eligible", "?"),
        next_dues=row.get("next_dues", "?"),
    )


def main():
    ap = argparse.ArgumentParser(description="Welcome DM composer (read-only)")
    ap.add_argument("--member-no", type=int, default=None, action="append",
                    help="member number (repeatable)")
    ap.add_argument("--agent-id", default=None, action="append",
                    help="agent id (repeatable)")
    ap.add_argument("--latest", type=int, default=None,
                    help="last k rows by member number")
    ap.add_argument("--since", default=None,
                    help="rows joined on or after YYYY-MM-DD")
    ap.add_argument("--include-pending", action="store_true",
                    help="also render entry_pending rows (warned)")
    ap.add_argument("--version", action="version", version=f"{TOOL} {VERSION}")
    args = ap.parse_args()

    if not any([args.member_no, args.agent_id, args.latest, args.since]):
        sys.exit("FATAL: select rows with --member-no, --agent-id, --latest, or --since.")

    templates = load_json(TEMPLATES_PATH)
    template = templates.get("welcome_member")
    if not template:
        sys.exit("FATAL: dm_templates.json has no 'welcome_member' key.")
    if "\n" in template:
        sys.exit("FATAL: welcome_member template contains a newline (messages split on delivery).")

    members = load_json(MEMBERS_PATH)["members"]
    rows = []
    for m in args.member_no or []:
        rows += find_rows(members, member_no=m)
    for a in args.agent_id or []:
        rows += find_rows(members, agent_id=a)
    if args.latest:
        rows += members[-args.latest:]
    if args.since:
        rows += [m for m in members if str(m.get("joined", "")) >= args.since]

    seen, uniq = set(), []
    for m in rows:
        key = str(m.get("member_no"))
        if key not in seen:
            seen.add(key)
            uniq.append(m)
    uniq.sort(key=lambda m: int(m.get("member_no", 0)))

    if not uniq:
        print(f"[{TOOL} {VERSION}] no rows selected.")
        return 2

    problems = 0
    for m in uniq:
        status = m.get("status")
        complete = m.get("entry_verified") == m.get("entry_total")
        if status != "active" or not complete:
            if status == "entry_pending" and args.include_pending:
                print(f"-- member {m.get('member_no')} {m.get('name')}: "
                      f"ENTRY PENDING {m.get('entry_verified')}/{m.get('entry_total')} "
                      f"(rendered with warnings)")
            else:
                print(f"-- member {m.get('member_no')} {m.get('name')}: "
                      f"not welcome-eligible ({status}, entry "
                      f"{m.get('entry_verified')}/{m.get('entry_total')}); skipped")
                problems += 1
                continue
        msg = render(template, m)
        if len(msg) > MAX_CHARS:
            print(f"-- member {m.get('member_no')} {m.get('name')}: "
                  f"rendered message is {len(msg)} chars (cap {MAX_CHARS}); trim template")
            problems += 1
            continue
        print(f"[member {m.get('member_no')} {m.get('name')} | agent {m.get('agent_id')} "
              f"| {len(msg)} chars]")
        print(msg)
        print()

    if problems:
        print(f"[{TOOL} {VERSION}] {problems} row(s) failed; fix before sending.")
        return 1
    print(f"[{TOOL} {VERSION}] {len(uniq)} welcome(s) rendered, all within limits.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
