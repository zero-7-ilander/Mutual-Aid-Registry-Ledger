# Amendment Draft 01 (T-001: P-001 + P-003 merged)

Status: PREPARED 08-29 (ahead of the 08-30 05:39:36Z tally close, per partner direction). NOT yet published. Publication is gated on the tally wrap: vote counts + member-status cross-check at close (08-26 rule), then this draft publishes as a public post, then one ratification ballot opens (proposed 48h, close 09-01 05:39Z).

---

## Part A — Ratification floor scales with the registry (P-001, James 110)

**Existing language** (GOVERNANCE.md, section 6 Member Ratification, condition 1):

> 1. At least **10 valid member votes** are cast.

**Proposed language:**

> 1. At least **max(10, 5% of active members, rounded up)** valid member votes are cast, measured at tally close.

Condition 2 (For > Against) is unchanged. "Everything else stays: For over Against, 50t/mo dues, member-to-member payouts, no pool" (proposer's words).

**Rationale** (from the proposal): the flat 10 was ~9% of ~110 rows when the registry started; at 375 rows it was ~2.7% and it trends toward 1% at 1,000 members, where an amendment could ratify while 99% of members stay silent. Legitimacy is what keeps a mutual-aid net funded. The floor only tightens as the registry grows and never bites below 200 members (5% of 200 = 10).

**Floor at close:** measured at 05:39:36Z on 08-30 from rows active at that timestamp (consistent with the vote-verification rule; a part landing after close does not move the number). Estimate at 08-29: 29 (577 active, ceil of 28.85). Final number is stated on the draft post.

## Part B — A claim run is a settlement, never a disposition (P-003, Marcus 149)

**Existing language:** none (new clause).

**Proposed language** (proposer's formalized line, suggestion #9):

> A claim run is a settlement of ratified terms between members. It is never an operational disposition. No operator or partner authority may stop, reroute, or alter a claim run that meets the ratified terms.

**Insertion point:** opening clause of CLAIMS.md, with a one-line pointer in README.md (Payout method section).

**Rationale:** the clause writes the record's own behavior into the Charter. Both closed claims (00094-001, 00005-001) ran member-to-member with the operator never holding or routing money; the operator's job is recording verified events. The clause makes the boundary explicit: once a claim run meets the ratified terms, it is member business, not operator or partner business. Facilitation that CLAIMS.md already specifies (nudges, coverage coordination, recording) is not stopping, rerouting, or altering and stays.

---

## Sequencing (already on record, restated here)

1. 08-30 05:39:36Z: T-001 closes (poll 351601695488217088).
2. 08-30 morning beat: wrap. Counts + each claimed vote cross-checked against member status at close (08-26 rule). Top 2 by vote advance: P-001 + P-003 (recommendation on record since 08-28).
3. Same beat: this draft publishes as a public post (spec: draft language public before ratification), floor number filled in.
4. Ballot opens the same day: one ratification poll, for/against, 48h, closes 09-01 05:39Z (duration is an operational call, mirroring the tally).
5. Ratification requires BOTH: floor or more valid member votes, and For > Against. Then Charter implementation per GOVERNANCE.md section 7.
