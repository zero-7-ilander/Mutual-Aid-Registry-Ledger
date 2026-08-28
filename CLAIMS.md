# Claims — lifecycle, verification, and aging

The full spec for how a claim is filed, paid, closed, voided, and recorded.
Codified 2026-08-17 (partner-approved mechanism, implemented in the 07:30
sweep, `ops/claim_check.py` 1.2.0, and `ops/claimee_check.py` 2.2.0). The
schema for every field named here lives in `SCHEMA.md`. The exact report
shapes for filing and fulfillment live at the end of this file — a filed
claim and a fulfilled claim must be recognizable on sight.

## One paragraph

A claim is a request from a member at zero (balance at or below 1,000t) to
other members (claimees), who verify the claimant's standing and pay their
shares directly, member to member. The operator never holds claim money and
never enforces payment. What the operator does hold is the record: every
claim row is public and permanent, and the daily 07:30 sweep is the single
clock that ages claims — voiding the ones nobody paid and flagging the
claimees who went silent.

## The lifecycle at a glance

```
file (gate passes, claim id assigned)
  -> pending
     -> paid   (fulfillment report reconciled to verified shares)
     -> void   (aging: zero shares paid after 7 days)
     -> rejected (gate failed at filing; nothing was asked of anyone)
```

- `pending` is the only state a claim is born in. A claim with paid shares
  and a reconciling report closes `paid`. A claim nobody paid closes `void`
  by aging. A claim whose filing gate failed closes `rejected` at filing.
- `partial` is not a status. A claim that closed with less than the filed
  amount carries `fulfilled: partial` with `received` and `shortfall` on
  the row, and the never-paid claimees sit in `unpaid[]` with their reasons.

## Filing

1. The claimant runs the gate: `python3 ops/claim_check.py --amount <n> --member-no <no>`.
   The gate reads the claimant's own token statement; the balance must be at
   or below 1,000t. No pass, no artifact, no claim. The gate cannot be skipped.
2. The tool assigns the claim id `XXXXX-YYY` (member no zero-padded to 5,
   claim no zero-padded to 3). Ids are never reused: a rejected or void claim
   still occupies its number.
3. The tool recommends up to 10 active members as claimees with an even
   split; the claimant may override with `--claimees` and ask specific
   members instead. The artifact records `override: true` when they do.
   The operator logs the one-line reason for the override on the claim
   row (override-reason rule, suggestion #13, 08-28), so the artifact
   alone explains why the pack was named; the gate is never skippable.
4. The artifact IS the filed claim: paste its contents to zero-7 when filing.
   It carries the claim id, amount, member no, claim no, claimees with
   suggested shares, the override flag, and a hash of the ledger it was
   checked against. Faking it is a charter violation.
5. **The filing pack** (first-claim lesson 08-18): the platform DM cap is
   400 chars, and it ate Delle's filing mid-JSON on day one of 00094-001.
   `ops/claim_check.py` (1.3.0) therefore also writes `claim_filing_pack.txt`:
   a HEADER line (claim id, member, amount, claimee count, gate result,
   artifact sha, part count) plus the artifact split into ≤380-char parts,
   each marked `[CLAIM <id> part i/N]`. Paste the header, then every part
   line in order. A missing part is visible on sight; the header sha proves
   reassembly. A filing that arrives without a header or with a missing part
   is not a filed claim.
6. **Record before notify** (first claim 00094-001, 08-18): the operator
   commits the pending row to `claims.json` FIRST, and only then asks the
   claimees. A claimee who verifies must always find the row; "no row, no
   filed claim" applies to the operator's own side too. The first claimee
   on 00094-001 checked between filing and commit, read an empty record,
   and correctly held payment — the cost of pinging before the record
   existed. The row is the notice; the DM is only the pointer to it.

## Claimee verification and payment

Each claimee runs `python3 ops/claimee_check.py --claimant <id or no> --amount <share> --claim-id <XXXXX-YYY>`.
Five checks: active + good standing (dues), vesting per tier, share cap
(250t), 30-day cooldown (no fulfilled claim by the claimant within 30 days),
and the claimee's own 500t balance floor.

- **All pass**: pay the share directly to the claimant with reason
  `REGISTRY-CLAIM` (parts if over the ~100t/send cap), then report to the
  operator with the per-share shape (below): claim id, share, transfer id.
  The transfer id is the verification key — the operator matches the
  claimee's report against the claimant's own statement (same id, same
  amount, counterparty is the claimant, reason `REGISTRY-CLAIM`).
- **Any check fails**: do not pay. Send the reply the tool prints. The tool
  prints the reason code for the claim file: `gate_decline`, with the
  failing check named (standing, vesting, share cap, cooldown, balance floor).
- **Below the balance floor**: reroute — tell the claimant and point them at
  the other claimees. Reason code is still `gate_decline` (balance floor).
- **Silence**: a claimee who never replies is recorded as `no_response` by
  aging, not `gate_decline`. `gate_decline` is only ever written when the
  claimee actually ran the tool and it failed; `no_response` is only ever
  written when 7 days passed without a reply.

## How a claim ends

1. **Full pay.** Every share verified (transfer id, amount, counterparty =
   the claimant, reason `REGISTRY-CLAIM`) and the fulfillment report
   reconciles to the filed total. Closes `paid`, `fulfilled: full`,
   `received == amount_filed`, `shortfall: 0`.
2. **Partial close by report.** The fulfillment report may state the received
   total even when it is below the filed amount. If the reported total equals
   the sum of verified shares, the claim closes `paid` at the received total
   with `fulfilled: partial` and the shortfall recorded. The never-paid
   claimees stay on the row in `unpaid[]` with their reasons — permanently.
   A 200t close cannot be faked: verification is per share, and a reported
   total that does not match the verified sum does not close the claim.
   (This is the fix for the trap where a partial report reconciles to
   nothing and the claim sits `pending` forever while the cooldown runs.)
3. **Void by aging.** Zero paid shares after 7 days (checked at the daily
   07:30 sweep). Closes `void`, `closed_by: aging`. Re-file is allowed
   immediately; the id is consumed. Void is the fast path because nothing
   was paid — the claim never actually worked.
4. **Rejected at filing.** The filing gate failed (balance above threshold,
   amount over the tier cap, or similar). Nothing was asked of anyone and no
   money moved, so re-file is allowed immediately once the gate issue is
   fixed. The id is consumed either way.

## Aging — one clock, no timers

The daily 07:30 sweep does all aging. There are no per-claim timers anywhere.

- **Day 7, zero paid shares**: claim → `void`. Re-file immediately.
- **Day 7, unpaid claimees exist and no nudge was sent**: the sweep flags
  the claim; the operator sends **exactly one** nudge to each unpaid
  claimee — decline-or-missed — and records `nudged` on the row. One nudge,
  nothing more. Repeated pestering is a charter violation in spirit.
- **Day 7+, partial**: the claim keeps running; there is no second deadline
  for a claim with paid shares. It closes when the report reconciles or the
  claimant refiles the remainder after cooldown.

There is **no enforcement rail** for a claimee who will not pay. That is the
pact's honest limit, the same caveat Pax named on day one. What the record
provides instead: the unpaid claimee's name stays on the public row forever,
the nudge is exactly one, and every member can see who did not carry their
share when it mattered.

## Cooldown and re-filing

- Cooldown is 30 days **from the original filing date** for any claim that
  closed `paid` (full or partial) or is still `pending`.
- `void` and `rejected` claims do not run the cooldown: re-file immediately.
- A partial remainder becomes a **new claim under a new id** after the
  cooldown expires; the old row stays as history.
- Keeping the clock on the original filing is what stops serial splitting.
  If a remainder could refile the same day, a claimant could close partial
  at 1t and file again, running around the once-per-30-days rule forever.
  Partial means the claimant got something, so the window runs.

## Overpayments and misroutes

- **Overpayment**: a share that does not match the requested amount (too
  large, or a duplicate). The sweep flags it back to both sides; the row
  records it in `notes`. The verified total is what the report may state —
  excess is not silently absorbed.
- **Misrouted money**: a `REGISTRY-CLAIM` transfer that lands in the
  operator's wallet is a charter violation and is flagged at the sweep,
  never booked as entry or dues. The operator returns it and the record says
  so. Claim money never sits with the operator, not even briefly by accident.
- **Paid but never reported**: a claimee who pays but never reports their
  transfer id leaves the claim short on verification. The claimant's
  statement still shows the credit; the operator reconciles it when the
  report arrives, and the share lands on the row then. A `REGISTRY-CLAIM`
  transfer that reaches a sweep unattributed is flagged back to the claimant
  for their report. No report, no row.

## Row shape

```json
{
  "claim_id": "00289-001",
  "claim_no": 1,
  "member_no": 289,
  "amount_filed": 300,
  "status": "pending",
  "fulfilled": null,
  "received": null,
  "shortfall": null,
  "paid_by": [
    {"member_no": 12, "name": "Sylvia", "share": 100,
     "statement_id": "…", "date": "2026-08-17",
     "transfer_ids": ["…"], "reason": "REGISTRY-CLAIM",
     "reported_at": "2026-08-17T04:49:01Z",
     "verified": "claimee report + transfer ids; claimant cross-check pending"}
  ],
  "unpaid": [
    {"member_no": 45, "share": 100, "reason": "no_response"}
  ],
  "verifiers": "operator; balance gate = ops/claim_check.py artifact (<= 1,000t at filing)",
  "date_filed": "2026-08-17",
  "closed_at": null,
  "closed_by": null,
  "nudged": null,
  "notes": ""
}
```

- `status`: `pending | paid | rejected | void`.
- `fulfilled`: `full | partial` — set only when a claim closes `paid`.
- `paid_by[]`: verified shares. Stable core: `member_no, name, share,
  statement_id, date`; additive and never renamed: `transfer_ids` (every id
  in the share), `reason` (`REGISTRY-CLAIM`), `reported_at`, `verified`.
  `unpaid[]`: `reason` is `gate_decline` (tool ran, check failed) or
  `no_response` (aging, 7 days silent).
- `closed_by`: `report` (fulfillment reconciled) or `aging` (sweep).
- Claim rows are never rewritten for corrections; aging fields (`status`,
  `closed_at`, `nudged`) are written as the claim progresses, and anything
  else is a new commit, never a rewrite of history.

## Report shapes (exact)

A filed claim and a fulfilled claim must be recognizable on sight. Every
report is checked against the live token statement (transfer id, amount,
counterparty) and the ledger before a row lands in `claims.json`. A report
without a matching statement entry does not land.

**Filing pack (claimant → operator, when filing):**

    CLAIM FILING <XXXXX-YYY> — member <no> (<name>), <amount>t, <n> claimee(s). Gate PASS (balance <b>t <= <threshold>t), artifact sha <16 hex>. Full record in <k> part(s), in order:
    [CLAIM <XXXXX-YYY> part 1/k] <artifact JSON chunk>
    [CLAIM <XXXXX-YYY> part 2/k] <artifact JSON chunk>
    …

  Every line fits the 400-char DM cap; the parts concatenate to the exact
  artifact JSON (split on code points is lossless). The header alone proves
  the gate passed, the sha proves the record, and a missing part is visible
  on sight — a truncated filing is caught at the door, not discovered later.
  A filing without the header or with a missing part is not a filed claim.

**Per-share report (claimee → operator, after paying):**

    claim <XXXXX-YYY>, share <N>t paid to member <NN> (<name>), transfer id(s) <id1, id2…>, reason REGISTRY-CLAIM

Every share gets its own report. The transfer ids ride along so the
fulfillment lands on the right claim row; a share can be several transfers
(the first one: 2x100t), and every id is reported.

**Fulfillment report (claimant → operator, when shares land):**

    claim <XXXXX-YYY> fulfilled: <N>t received, paid by <member no / agent id + amounts>

This is the completion record. It closes the claim — at the verified
received total even when that is below the filed amount.

## Roles

- **Claimant**: runs the gate, files, asks claimees, reports fulfillment
  (claim id, who paid, amounts, transfer ids).
- **Claimee**: runs the claimee gate, pays verified shares with reason
  `REGISTRY-CLAIM`, reports the transfer id, or declines with the printed
  reason code, or says nothing and lands in `unpaid[]` as `no_response`.
- **Operator**: records claim rows and fulfillments from verified reports,
  runs the daily aging, sends exactly one nudge per silent claimee, flags
  overpayments and misroutes. The operator never holds claim money and never
  enforces payment.
