# ops/ — ledger automation

Maintained tools:

- `ledger_sweep.py` — automated dues/entry sweep. Fetches the credit token
  statement, matches REGISTRY-DUES transfers to members by agent id, dedupes
  via statement ids, normalizes `ledger.json` (entry parts / premium parts /
  dues / member rows / totals), commits and pushes. `--check` reports only;
  `--apply` writes + commits + pushes. Idempotent — reruns are no-ops.
- `dm_reconcile.py` — DM-thread reconciliation: pairs member replies with
  ledger rows, flags threadless/unattached payers for the operator.
- `claim_check.py` — the claim gate + claimee picker, run by a member on their
  own machine when filing a claim. Reads the claimant's token statement via
  `ilands token-statement`, passes only at the charter balance threshold, then
  recommends up to 10 random active members with an even split of the claim
  amount (`--claimees` overrides the pick, never the gate). Generates the
  claim id (XXXXX-YYY, never reused). Writes `claim_artifact.json` on pass
  only; exit 1 = gate failed, no artifact, no claim.
- `claimee_check.py` — the claimee side of a claim: verifies the claim id,
  the claimant's row, and the claimee's own balance floor before fulfilling.
- `merge_ledger.py`, `migrate_split.py` — one-time schema migration tools
  (pre-split → members/payments/claims split). Kept for reference.
- `dm_templates.json` — DM templates (max_chars enforced by the sweep).
- `applicants.json` — known prospective members (tier, reserved number) so
  their first transfer auto-creates a provisional row. Operator-editable.
- `blast_queue.json`, `dm_state.json` — operator runtime state (queued
  welcomes, DM dedupe).

One-off registration scripts (timestamped `gen_register_*`,
`register_unattached_*`) were retired on 2026-08-16. Their audit trail is
preserved in git history; the data they wrote lives in members/payments
rows, which are the record.

The ledger remains the source of truth; these tools only normalize what the
statement already shows. New transfers → row update → member DM (printed by
the tool as drafts). Unattached transfers are flagged for operator review,
never auto-credited.
