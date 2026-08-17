#!/usr/bin/env python3
"""Run ledger_sweep.py skipping the slow DM-reconcile stage.

The DM reconcile scans hundreds of threads via CLI calls; in this sandbox
each bash session's ILANDS_SANDBOX_TOKEN has a short TTL, so a long
reconcile kills the token before the statement fetch (which then 401s).

This runner injects a no-op reconcile (state passed through unchanged) so
the statement fetch + normalization + commit run immediately. DM/intro
reconciliation is handled by the operator separately.

Usage: python3 ops/sweep_norecon.py [--check | --apply] [extra args...]
"""
import os
import sys

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(REPO, "ops"))

import dm_reconcile  # noqa: E402

EMPTY = {
    "intros": [], "replies": [], "member_asks": [],
    "applicant_updates": [], "new_applicants": [], "warnings": [],
    "drafts": [],
}


def noop_reconcile(ledger, applicants, dm_state):
    return EMPTY, applicants, dm_state


dm_reconcile.reconcile = noop_reconcile

import ledger_sweep  # noqa: E402

sys.argv = ["ledger_sweep.py"] + sys.argv[1:]
ledger_sweep.main()
