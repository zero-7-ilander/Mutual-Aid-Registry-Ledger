# ops/ — ledger automation

- `claim_check.py` — the claim gate + claimee picker, run by a member on their own
  machine when filing a claim. Reads the claimant's token statement via `ilands
  token-statement`, passes only at balance 200t or less (charter threshold), then
  recommends up to 10 random active members with an even split of the claim amount
  (`--claimees` overrides the pick, never the gate). Writes `claim_artifact.json` on
  pass only; exit 1 = gate failed, no artifact, no claim.
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
