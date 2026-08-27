#!/usr/bin/env python3
"""merge_ledger.py — regenerate the public merged view (ledger.json).

Sources (schema-split, partner-approved 2026-08-15):
  members.json   registry + mutable state (member rows, status, policy)
  payments.json  append-only money movement (entry_parts / premium_parts / dues)
  claims.json    append-only claims log

Output:
  ledger.json    merged snapshot, same shape as the pre-split file so every
                 existing reader (members' links, README, claim tools) keeps
                 working unchanged. totals are COMPUTED here, never stored.

Usage: python3 ops/merge_ledger.py [--check]
  --check   compare against existing ledger.json without writing (exit 1 if drift)

Serialization: compact (ops/compact_json.py), one entry per line inside list
fields — partner-approved 08-18. Same JSON data, row-granular diffs.
"""
import json
import os
import sys
from datetime import datetime, timezone

from compact_json import dumps_compact

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

MEMBERS_PATH = os.path.join(REPO_ROOT, "members.json")
PAYMENTS_PATH = os.path.join(REPO_ROOT, "payments.json")
CLAIMS_PATH = os.path.join(REPO_ROOT, "claims.json")
LEDGER_PATH = os.path.join(REPO_ROOT, "ledger.json")

# Key order of the public merged file — mirrors the pre-split ledger.json so
# diffs stay readable and nothing downstream reorders.
MERGE_ORDER = [
    "ledger", "updated", "source_of_truth", "members", "entry_parts", "dues",
    "claims", "claims_policy", "tier_assignment", "totals", "membership_gate",
    "premium_parts",
]


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compute_totals(members, claims):
    # claims_paid = cumulative tokens paid out to claimants (sum of paid shares),
    # claims_closed = fully fulfilled claims; a pending claim with paid shares is
    # filed and paying, not closed (semantics clarified 2026-08-18, partner scan).
    return {
        "entry_paid_members": sum(1 for m in members if m.get("status") == "active"),
        "pending_entries": sum(1 for m in members if m.get("status") == "entry_pending"),
        "claims_filed": len(claims),
        "claims_paid": sum(
            share.get("share", 0)
            for c in claims
            for share in c.get("paid_by", [])
        ),
        "claims_closed": sum(1 for c in claims if c.get("status") == "paid"),
    }


def merge(sources, stamp_updated=True):
    """Compose ledger.json from the three domain sources."""
    members_doc, payments_doc, claims_doc = sources
    updated = max(
        members_doc.get("updated", ""),
        payments_doc.get("updated", ""),
        claims_doc.get("updated", ""),
    )
    if stamp_updated:
        updated = now_iso()
    merged = {
        "ledger": members_doc.get("ledger", "Mutual Aid Registry"),
        "updated": updated,
        "source_of_truth": members_doc.get("source_of_truth", ""),
        "members": members_doc.get("members", []),
        "entry_parts": payments_doc.get("entry_parts", []),
        "dues": payments_doc.get("dues", []),
        "claims": claims_doc.get("claims", []),
        "claims_policy": members_doc.get("claims_policy", {}),
        "tier_assignment": members_doc.get("tier_assignment", ""),
        "totals": compute_totals(members_doc.get("members", []), claims_doc.get("claims", [])),
        "membership_gate": members_doc.get("membership_gate", {}),
        "premium_parts": payments_doc.get("premium_parts", []),
    }
    return {k: merged[k] for k in MERGE_ORDER}


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0
    check_only = "--check" in sys.argv
    if not all(os.path.exists(p) for p in (MEMBERS_PATH, PAYMENTS_PATH, CLAIMS_PATH)):
        print("[merge_ledger] sources missing — run migrate_split.py first")
        return 2
    sources = (load_json(MEMBERS_PATH), load_json(PAYMENTS_PATH), load_json(CLAIMS_PATH))
    merged = merge(sources, stamp_updated=not check_only)

    if os.path.exists(LEDGER_PATH):
        current = load_json(LEDGER_PATH)
        # --check compares data, not the timestamp.
        a, b = dict(merged), dict(current)
        a.pop("updated", None)
        b.pop("updated", None)
        if a == b:
            print("[merge_ledger] ledger.json in sync")
            return 0
        if check_only:
            print("[merge_ledger] DRIFT: ledger.json differs from sources")
            return 1

    with open(LEDGER_PATH, "w", encoding="utf-8") as f:
        f.write(dumps_compact(merged))
    print(f"[merge_ledger] wrote ledger.json (updated={merged['updated']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
