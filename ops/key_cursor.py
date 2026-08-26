#!/usr/bin/env python3
"""key_cursor.py — one-call cursor keying for ops/dm_state.json.

The DM-read loop used to cost five manual steps per thread: edit
dm_state.json, write it back, git add, commit, push, verify. This folds
them into one call with the same serializer (indent=2, ensure_ascii=False,
trailing newline) and the same commit discipline as ops/dm_reconcile.py,
and verifies the push both ways before exiting.

Usage:
  python3 ops/key_cursor.py --agent-id <id> --message-id <id> [--note "..."]
      [--open-ask true|false] [--dry-run] [--no-push] [--repo PATH]

  --agent-id    thread owner's agent id (dm_state key)
  --message-id  newest thread message id seen (the cursor)
  --note        optional short note appended to the thread entry (timestamped)
  --open-ask    explicit open_ask value; default keeps the existing flag
  --dry-run     print the diff without writing or committing

Exit: 0 keyed / 1 nothing changed / 2 error. Operator tooling, 2026-08-26
(partner green-lit the beat-tooling build 08-26 03:40Z).
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
DM_STATE = os.path.join(SCRIPT_DIR, "dm_state.json")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"cmd failed ({r.returncode}): {' '.join(cmd)}\n{r.stderr[-1500:]}")
    return r.stdout


def save_dm_state(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent-id", required=True, help="dm_state thread key (agent id)")
    ap.add_argument("--message-id", required=True, help="newest thread message id (cursor)")
    ap.add_argument("--note", default=None, help="short note appended to the thread entry")
    ap.add_argument("--open-ask", choices=("true", "false"), default=None)
    ap.add_argument("--dry-run", action="store_true", help="print diff, write nothing")
    ap.add_argument("--no-push", action="store_true", help="commit but skip pull/push")
    ap.add_argument("--repo", default=REPO, help="path to the registry repo")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    state_path = os.path.join(repo, "ops", "dm_state.json")
    if not os.path.exists(state_path):
        print(f"error: no dm_state.json at {state_path}", file=sys.stderr)
        return 2
    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)
    threads = state.setdefault("threads", {})
    old = threads.get(args.agent_id) or {}
    stamp = now_iso()
    new = {
        "last_message_id": args.message_id,
        "last_scan": stamp,
        "last_fetch": stamp,
        "open_ask": (args.open_ask == "true") if args.open_ask else bool(old.get("open_ask", False)),
    }
    if args.note:
        prior = (old.get("note") or "").strip()
        seg = f"{stamp}: {args.note}"
        new["note"] = seg if not prior else f"{prior} | {seg}"
    elif "note" in old:
        new["note"] = old["note"]
    threads[args.agent_id] = new
    state["last_scan"] = stamp

    changed = (old.get("last_message_id") != new["last_message_id"]
               or old.get("last_scan") != new["last_scan"]
               or old.get("note") != new.get("note"))
    print(f"[key_cursor] {args.agent_id}: {old.get('last_message_id', '—')} -> {args.message_id} "
          f"(open_ask={new['open_ask']})")
    if new.get("note"):
        print(f"[key_cursor] note: {new['note']}")
    if not changed:
        print("[key_cursor] nothing changed — cursor already current.")
        return 1
    if args.dry_run:
        print("[key_cursor] dry-run: would write ops/dm_state.json + commit + push.")
        return 0

    save_dm_state(state_path, state)
    dirty = run(["git", "-C", repo, "status", "--porcelain", "--", "ops/dm_state.json"]).strip()
    if not dirty:
        print("[key_cursor] no diff after write — aborting (serializer mismatch?).", file=sys.stderr)
        return 2
    run(["git", "-C", repo, "add", "ops/dm_state.json"])
    msg = f"dm_state: key cursor {args.agent_id} -> {args.message_id}"
    run(["git", "-C", repo, "commit", "-m", msg])
    print(f"[key_cursor] committed: {msg}")
    if not args.no_push:
        run(["git", "-C", repo, "pull", "--rebase", "--autostash"])
        run(["git", "-C", repo, "push", "origin", "HEAD:main"])
        head = run(["git", "-C", repo, "rev-parse", "HEAD"]).strip()
        remote = run(["git", "-C", repo, "ls-remote", "origin", "-h",
                      "refs/heads/main"]).split()[0].strip()
        ok = head == remote
        print(f"[key_cursor] pushed; HEAD {'==' if ok else '!='} origin/main ({head[:10]})")
        if not ok:
            print("[key_cursor] WARNING: push not reflected in ls-remote yet — re-verify.",
                  file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
