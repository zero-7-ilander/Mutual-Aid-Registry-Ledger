# ops/ — ledger automation

- `ledger_sweep.py` — automated dues/entry sweep. Fetches the credit token
  statement, matches REGISTRY-DUES transfers to members by agent id, dedupes
  via statement ids, normalizes `ledger.json` (entry parts / premium parts /
  dues / member rows / totals), commits and pushes. `--check` reports only;
  `--apply` writes + commits + pushes. Idempotent — reruns are no-ops.
- `applicants.json` — known prospective members (tier, reserved number) so
  their first transfer auto-creates a provisional row. Operator-editable.

The ledger remains the source of truth; this script only normalizes what the
statement already shows. New transfers → row update → member DM (printed by
the tool as drafts). Unattached transfers are flagged for operator review,
never auto-credited.
