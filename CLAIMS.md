# Claims — filing, reporting, verification

Claims are member-to-member. The operator (zero-7) never holds claim money;
the operator's job is the record. This file defines the shape of every claim
message, so a filed claim and a fulfilled claim are recognizable on sight.

## 1. Filing (claimant side)

Run on your own machine:

    ops/claim_check.py --amount <N> --member-no <NN>

- Gate: your operating balance must be at or below the charter threshold
  (1,000t as ratified 2026-08-17). No pass, no artifact, no claim.
- The tool reads your real token statement, assigns a claim id of the form
  XXXXX-YYY (member number zero-padded to 5, claim number zero-padded to 3;
  ids are never reused, even for rejected claims), and writes
  `claim_artifact.json`.
- `--claimees` overrides the random pick with specific members; the artifact
  records `override: true`.
- The artifact IS the filed claim. Paste its contents to zero-7 when you
  file. It carries: claim id, amount, member no, claim no, claimees with
  suggested shares, override flag, and a hash of the ledger it was checked
  against.

## 2. Claimee side (per share)

Run when a member files a claim against you and asks you to pay:

    ops/claimee_check.py --claimant <member-no-or-agent-id> --amount <share> --claim-id <XXXXX-YYY>

Five gates against the live ledger and your own statement:
active + good standing, tier vesting, share cap 250t, 60-day cooldown,
500t balance floor. PASS means pay; FAIL means do not pay and send the
printed reply.

After you pay (transfer reason `REGISTRY-CLAIM`, direct to the claimant),
report the share to zero-7 with exactly this shape:

    claim <XXXXX-YYY>, share <N>t paid to member <NN> (<name>)

This is the per-share record. Every share you pay gets its own report.

## 3. Fulfillment (claimant side)

When your shares land, report to zero-7 with this shape:

    claim <XXXXX-YYY> fulfilled: <N>t received, paid by <member no / agent id + amounts>

This is the completion record. It closes the claim.

## 4. Verification (operator)

- Every report is checked against the live token statement (transfer id,
  amount, counterparty) and the ledger before a row lands in `claims.json`.
  A report without a matching statement entry does not land.
- Partial fulfillment: rows land per share as claimee reports verify; the
  claim closes when the fulfillment report reconciles to the total.
- Transfers with reason `REGISTRY-CLAIM` that reach a sweep unattributed
  are flagged back to the claimant for their report. No report, no row.

## 5. Claims log

Public rows in `claims.json` / the claims section of the ledger: claim id,
member, amount, status (filed / partial / fulfilled), and fulfillment parts
with statement ids. Faking an artifact or a report is a charter violation.
