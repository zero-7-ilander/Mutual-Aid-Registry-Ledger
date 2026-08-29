#!/usr/bin/env python3
"""SUMMARY.md generator — the record answers without being asked.

Regenerates the one-line as-of snapshot at repo root from the canonical
files (members.json + claims.json). Called by ledger_sweep.py on every
--apply so the snapshot never drifts from the ledger; also runs
standalone. If this file ever disagrees with ledger.json totals, the
ledger wins — the summary is a mirror, not a source.
"""

import json
import os
import sys
from datetime import datetime, timezone


def load_json(path):
    with open(path) as f:
        return json.load(f)


def write_summary(repo_root, ledger=None):
    members = load_json(os.path.join(repo_root, "members.json"))["members"]
    claims = load_json(os.path.join(repo_root, "claims.json"))["claims"]

    statuses = {}
    for m in members:
        s = m.get("status", "unknown")
        statuses[s] = statuses.get(s, 0) + 1
    active = statuses.get("active", 0)
    pending = statuses.get("entry_pending", 0)
    departed = statuses.get("departed", 0)

    filed = len(claims)
    closed = sum(1 for c in claims if c.get("status") == "paid")

    asof = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    lines = [
        "# Registry Summary",
        "",
        f"As of {asof}: rows {len(members)} ({active} active / {pending} entry-pending / {departed} departed), "
        f"claims filed {filed}, paid and closed {closed}.",
        "",
        "Sources of truth: ledger.json (totals), members.json, claims.json. "
        "This snapshot is regenerated on every money-sweep apply. If it ever "
        "disagrees with ledger.json, the ledger wins.",
        "",
    ]
    summary_path = os.path.join(repo_root, "SUMMARY.md")
    with open(summary_path, "w") as f:
        f.write("\n".join(lines))
    return summary_path


if __name__ == "__main__":
    repo = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(write_summary(repo))
