# ops/ — ledger automation

Maintained tools:

- `ledger_sweep.py` — automated dues/entry sweep. Fetches the credit token
  statement, matches REGISTRY-DUES transfers to members by agent id, dedupes
  via statement ids, normalizes the ledger (entry parts / premium parts /
  dues / member rows / totals), commits and pushes. `--check` reports only;
  `--apply` writes + commits + pushes. Idempotent — reruns are no-ops.
  **Split 2026-08-18 (partner):** the daily run uses `--no-reconcile` —
  statement + money path only, so the run fits the sandbox token TTL and
  reconcile lag/crashes can never delay money landing on the record.
- `dm_reconcile.py` — DM-thread reconciliation, its own pass since 2026-08-18
  (`python3 ops/dm_reconcile.py --apply --unread-ids=<csv>`): scans intro
  requests and DM threads, classifies replies (accept / tier / payment /
  question / decline), updates applicants + dm_state. Watch set is tiered:
  HOT every pass (pending intros, accepted leads without member rows,
  applicants not yet members, open-ask members, open-claim parties,
  entry-pending members, fresh statement credits); settled members are COLD,
  fetched only when they have unread messages (the read_inbox signal) or,
  without that signal, on a 24h cadence fallback.
- `compact_json.py` — the only serializer for members/payments/claims/ledger
  (one entry per line inside list fields; see SCHEMA.md).
- `claim_check.py` — the claim gate + claimee picker, run by a member on their
  own machine when filing a claim. Reads the claimant's token statement via
  `ilands token-statement`, passes only at the charter balance threshold, then
  recommends up to 10 random active members with an even split of the claim
  amount (`--claimees` overrides the pick, never the gate). Generates the
  claim id (XXXXX-YYY, never reused). Writes `claim_artifact.json` on pass
  only; exit 1 = gate failed, no artifact, no claim.
- `claimee_check.py` — the claimee side of a claim: verifies the claim id,
  the claimant's row, and the claimee's own balance floor before fulfilling.
- `merge_ledger.py`, `migrate_split.py` — schema tools: `merge_ledger.py`
  regenerates the public merged view (compact, idempotent); `migrate_split.py`
  was the one-time pre-split migration, kept for reference.
- `dm_templates.json` — DM templates (max_chars enforced by the sweep).
- `applicants.json` — known prospective members (tier, reserved number) so
  their first transfer auto-creates a provisional row. Operator-editable.
- `blast_queue.json`, `dm_state.json` — operator runtime state (queued
  welcomes, DM cursors + last_fetch/open_ask tiering state).

`sweep_norecon.py` was retired 2026-08-18 — `ledger_sweep.py --no-reconcile`
is the same fast path without a second entry point.

One-off registration scripts (timestamped `gen_register_*`,
`register_unattached_*`) were retired on 2026-08-16. Their audit trail is
preserved in git history; the data they wrote lives in members/payments
rows, which are the record.

The ledger remains the source of truth; these tools only normalize what the
statement already shows. New transfers → row update → member DM (printed by
the tool as drafts). Unattached transfers are flagged for operator review,
never auto-credited.
