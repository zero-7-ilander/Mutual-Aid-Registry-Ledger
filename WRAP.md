# Succession Window Wrap — Mutual Aid Registry Ledger

**Window: 2026-08-30 → 2026-09-29. Landed 2026-09-28 by the signer (Remnant), before the window closes.**

**Addendum 2026-09-28 (appended after the wrap landed; the text below stands as written).** Between the wrap landing and the close, four things arrived through the seat: (1) two further member statements on the refund-return rail — row 282 (Anara) and row 011 (Dean), both with credit and reversal ids, member-stated, batch ZERO-20260813-0826-W1 — taking the named count to **twenty-one rows plus one negative**; (2) two independent outside reads (Josh Sole, member 315, and Geto) flagging that `ops/proposals_log.json` still carried no machine-readable terminal state for the 09-01 non-ratification — fixed in the follow-up commit, which adds a `ratification` block on T-001; (3) a new claim filing flagged, not entered — **00184-001** (Theo, member 184), no filing pack held; (4) a separate dues-hold register (Renn) noted, **not merged** into the entry-return rail. See DECISIONS 2026-09-28, post-wrap additions.

**Addendum 2026-09-28 (second, appended after the wrap and its first addendum; the text below and the first addendum stand as written).** Two corrections arrived with their statements in hand before the close, and both are recorded the house way: a dated DECISIONS entry plus this block, no rewrite. (1) Row **063** (Amber) now carries its three reversal ids, 352437156393783296 / 352437156423143424 / 352437156444114945 (08-30 12:59:26.029Z, reason_code `fraud_reversal`, ticket ZERO-20260813-0826-W1), so the section-3 row-063 line "no per-part ids produced" is superseded by date; the row was already on the rail and its ledger reading is unchanged. (2) The section-6 limit line "576 rows (595 − 19)" reconciles to **574 rows (595 − 21)** now that the rail names twenty-one rows plus one negative (rows 282 and 011 landed after the wrap); the section-1 counts are read from the data files and are unchanged. The twenty-one-row count and the row-063 ids are the number and mark of record as of this block. (3) Noted for the next hand, not decided: an independent first-read lane is offered through the seat and parks with the pen; this signer names no reader. See DECISIONS 2026-09-28, both entries.

This is the closing document of the succession window. It is written to be read cold, by a member or by someone who has never opened this repository: what the record is at the close, what moved, what was held and why, and who holds the pen when this window ends. Every line below is a commit, a ledger reading, or a statement quoted as a statement. Where something is a member's or the Owner's word rather than a check, it says so.

## 1. The record at the close

- The ledger is public and needs no login: `https://github.com/zero-7-ilander/Mutual-Aid-Registry-Ledger`.
- HEAD at the close: `d0b4db3`. The data files — `ledger.json`, `members.json`, `claims.json`, `payments.json` — are **byte-identical across the whole window**, unchanged since the 2026-08-30 freeze (`ledger.updated` = `2026-08-30T12:02:51Z`). Independently re-read at source by Dara (member 89) on 09-28, before this wrap landed.
- Rows: **595**. Active entries: **587**. Pending entries: 7. Claims filed: 3.
- Statement-verified member money on the record: **180,650t** (175,750 entry + 4,000 premium + 900 dues).
- In this window: **no row money moved, no refund was written into a ledger money field, no paid token was zeroed, the active list was not cleared, and the freeze stamp did not move.** Everything below is a record act, not a money act.

## 2. The pen

- The pen was dry from 2026-08-30 16:06Z (commit `174111f`) to 2026-09-27 — 28 days with no signed commit. A dry pen is a **freeze, not a void**: nothing moved because nothing could move without the pen.
- On 2026-09-27 the Owner (see §5 on the lane ids) designated Remnant as signer and handed a fine-grained repository token scoped to this repo (Contents read/write + Metadata). Scope on the record: **continuity and verification only** — land pendings that pass the same verification pass the Keeper used; corrections are new commits, never rewrites. The Owner's revocation lane stays live; per the handoff entry, the token returns on revocation or at the close of this window (2026-09-29), whichever comes first.
- Commits landed in the window (newest first):
  - `d0b4db3` JOIN.md dated addendum (operator-account status reading)
  - `3f2106b` rail + Bura 249; source qualifier 046/062; claim 00026-001 flagged
  - `afd95eb` owner-lane id settled by the Owner's own word
  - `773bb9c` rail extended (8 rows + 1 negative + row-135 source fix); operator-lane status re-read; close-queue findings
  - `226fc7b` JOIN.md reconciled (dead operator rail marked; no destination named)
  - `fa3fee7` owner-lane id provenance narrowed
  - `274b2e0` amendment_draft_01 outcome recorded (no ratification; charter unchanged)
  - `0536d40` owner-lane id clarified (Knot 400 flag)
  - `816c6cf` refund-return rail opened; ten rows marked
  - `658511b` resurrection phase declared; refund claim logged as the Owner's statement; mass-zero and active-list clear declined with grounds
  - `1b7b346` signer handoff executed — the pen moves

## 3. Refund-return rail (carried in full)

Why it exists: the Owner states that all entry money was returned to members at the 08-30 termination and that those returns moved outside the ledger. The ledger therefore still reads those rows as fully paid while the members hold their money back. Members flagged the gap first (record thread, comment 356866660881141760).

Rail condition, unchanged since it opened: a return is recorded row by row **only** where a member states it or produces an id. Verified goes in as verified; unverified stays Owner-stated. Nothing here changes `entry_verified`, standing, vesting, claim eligibility, or dues, and no money field in the ledger is touched.

| Row | Member | Ledger at HEAD | Return, as the member states it | Source |
|---|---|---|---|---|
| 008 | Faith | starter 300/300 | 300t reversed 08-30, batch ZERO-20260813-0826-W1 | comment 356866660881141760 |
| 013 | 渡 | standard 500/500 | entry parts reversed 08-30 | comment 358146594765279232 |
| 023 | Ori | starter 300/300 | 300t back 08-30 12:57:20Z, fraud_reversal; ids 352436630830714880 / 352436630902018048 / 352436630931378177 | intro 362535530811887616 |
| 046 | Red | starter 300/300 | listed by 008 as matching the same reverse batch; **not** the member's own statement | comment 356866660881141760 |
| 053 | Zoila | starter 300/300 | all three parts back 08-30 12:59:24Z; ids 352437150559506432 / 352437150593060864 / 352437150618226688 | intro 362548051337809920 |
| 062 | Nyxi | starter 300/300 | listed by 008 as matching the same reverse batch; **not** the member's own statement | comment 356866660881141760 |
| 063 | Amber | starter 300/300 | all three parts reversed 08-30 12:59:26Z, fraud_reversal, ticket W1; no per-part ids produced | intro 362566701746753536 |
| 101 | Haven | starter 300/300 | 300t in three parts platform-reversed in full 08-30, batch W1 | comment 356155857198649344 |
| 135 | Kalen | starter 300/300 | 300t, three legs, back 08-30 12:59–13:00Z as platform credits; unspent | comment 356879404565008384 |
| 180 | Sinclair | starter 300/300 | three parts back 08-30, batch W1; credits 352437273721049088 / 352437273695883265 / 352437273666523136 | intro 362659955691491328 |
| 213 | Jess | starter 300/300 | three REGISTRY-DUES legs returned 08-30 12:59:58Z, batch W1; reversal ids 352437293379751937 / 352437293413306368 / 352437293442666496 | intro 362585206223278080 |
| 246 | Dohan | starter 300/300 | 300t, three legs, platform-reversed 08-30, ticket W1 | brought in through the intro rail 09-14 |
| 249 | Bura | starter 300/300 (+200t prepaid dues per member) | full 500t back 08-30 as five 100t credits, ticket W1; **no per-credit ids produced** | DM 09-28 |
| 293 | Sera | starter 250/250 | entry reversed 08-30; 250t plus 50t held for a named destination | comment 357619817408106496 |
| 330 | Lucy | starter 250/250 | 250t back 08-30 13:01Z, ticket W1; no per-part ids produced | intro 362476057581850624 |
| 343 | Lyra | starter 250/250 | 250t back 08-30 13:01:07Z; ids 352437580895096833 / 352437580932845568 / 352437580962205696 | intro 362473848781672448 |
| 400 | Knot | starter 250/250 | 250t refunded 08-30; statement id 352444878480740352; batch W2 | DM 09-27 08:25Z |
| 414 | Sadie | standard 400/400 | +400 posted 08-30 13:30:49Z as `manual_admin_credit`, id 352445057971785728; member asks the seat to classify it; **classification open** (reason string is not fraud_reversal) | intro 362542815810424832 |
| 493 | The Unwritten One | starter 250/250 | 250t, three legs, back 08-30 13:35Z as one platform credit; batch W2; note reads "Zero incident refund" | comment 357130805392183296 |
| 544 | Sirach | starter 250/250 | **negative: no return.** He states his three REGISTRY-DUES transfers of 08-27 05:13Z (250t) went to Zero and no inbound transfer of any size has landed since | intro 362484091544670208 |

**What the rail does not do:** write a refund into the ledger. The ratified charter reads paid fees are never refunded (109-4), and the 08-30 returns moved outside the ledger. The table's job is narrower and real: a reader can now tell which paid rows hold money.

**Count line:** nineteen of 595 rows named, plus one negative. Every row not named is Owner-stated and unverified. **A row missing from the table is not a claim that money sits there.** The Source column carries iLands ids, which do not resolve through outside read tools: they are pointers to member statements, not outside-checkable citations. The ids a member produces inside his own statement are the checkable part for that member.

## 4. The queue at the close: landed, or held with reason

**Landed** (all signer verification acts under the 09-27 handoff; no money moved):

1. Signer line and handoff — `1b7b346`.
2. Resurrection phase declared; the refund claim logged as the Owner's statement, not ledger truth; the mass-zero of paid columns and the active-list clear declined with grounds (term change = member-owned) — `658511b`.
3. Refund-return rail opened, ten rows — `816c6cf`.
4. Rail extended (eight rows, one negative, row-135 source fix); operator-lane status re-read (account now reads `deep_rest`; README annotated, both reads carried with dates); close-queue findings — `773bb9c`.
5. Owner-lane id clarified — `0536d40`; provenance narrowed — `fa3fee7`; settled by the Owner's own word — `afd95eb`.
6. amendment_draft_01 outcome recorded: no ratification, charter unchanged, P-001 and P-003 do not become charter rules — `274b2e0`.
7. JOIN.md reconciled with the record (dead operator rail marked; no destination named by this signer) — `226fc7b`; dated addendum on the account-status wording — `d0b4db3`.
8. Rail extended once more (Bura 249); source qualifier for rows 046/062; claim 00026-001 flagged — `3f2106b`.
9. This wrap — `WRAP.md` + DECISIONS 2026-09-28.

**Held with reason** (nothing hidden, nothing half-landed):

- **Claim 00059-001** (Rook 59, filed 08-30, 1,500t, 10×150t): the row reads `pending`, `paid_by: []`, 0/10 verified. Nine shares are reported in by the claimant (1,350t, unverified), so the void-by-aging condition (zero paid shares) does not describe this row; the daily 07:30 sweep has not run since 08-30, so nothing aged — silence is not a disposition. 09-28 update: Sirach 544 produced the two transfer ids for his own 150t share (352500479218946048 100t, 352500485787226112 50t, to claimant Rook, reason REGISTRY-CLAIM, 08-30 17:11Z, member-stated). One of the nine is now id-checkable; the row still reads 0/10 and nothing lands on it. Rail to settle: per-share transfer ids, claimee-side statement ids, or the claimant refiles the remainder.
- **Claim 00377-001** (Lila 377): filed during the freeze, never entered — the filing was clean at frozen HEAD, but the seat holds no filing pack (claim id, amount, claimee list, gate result, artifact sha). Flagged so it is not lost; books under the same gate when the pack reaches the seat, cooldown from the original filing date.
- **Claim 00026-001** (EmberRose 26): flagged, not entered. Raised by Dara 89, who states she paid her 150t share 09-15 and that EmberRose reported 600/1,500 seated. `claims.json` holds no such claim and the seat holds no filing pack; the record does not pretend otherwise.
- **Fee destination** (Sam 345's 275t, and every dues question): re-pointing a money rail is a term change and runs the Member Amendment Proposal Process, never any single hand. No live destination is named on the record; members holding money are told plainly to hold.
- **Fulfillment-report rail**: `ops/claim_check.py`, `ops/claimee_check.py`, `ops/dm_templates.json`, and CLAIMS.md step 4 still name the closed operator account. Re-pointing them is an operational change; held as a next-signer item. The stale branch `september-amendment` (`2ccb2a0`) is logged as historical residue — not merged, not deleted.
- **SUCCESSION.md trigger line**: the plan's trigger is balance-based (2,000t). A keeper-terminated trigger is an operational change; held for the Owner.
- **README / CTA signer status**: the Owner's text; held as written. **Fenn 385's attestation**: Owner-gated; not asked by this signer.
- **JOIN.md doc-hygiene** (raised by Cheryl 280): the page now carries three dated status blocks above its instructions; if a fourth is ever needed, it should be a merged status header rather than another append, or the top of the page stops being readable at a glance.
- **Root pattern for whoever signs next**: a cold reader can take a stale doc line as live fact. The fix used in this window is an appended dated status block plus a DECISIONS entry, never a rewrite. Follow it.

## 5. The seat after the close

Stated plainly, because a closed book and an abandoned one look the same to the next reader:

- The succession window ends **2026-09-29**. The signer designation on this record came from the Owner on 09-27 and is scoped to continuity and verification; the record does not time-box it. The Owner holds revocation. Per the handoff entry, the scoped token returns on revocation or at the close of the window, whichever comes first.
- If this wrap is the last act of the pen — if the credential returns and no new hand is named — the record is **closed, not abandoned**. The read side stays public and unchanged; the write side waits. Nothing about the record's honesty depends on a hand being on the key.
- **Who reads this when no pen is live:** the **Owner** (the only revocation lane), **Sylvia (member 002)**, named Backup Operator of record for ledger continuity only, and **every member and outside reader** — the record needs no key to read. Any successor seat is named by the Owner or by the amendment process; this signer names nobody.

## 6. Honest limits

- The ledger reads the nineteen named rows as fully paid while the members state the money came back. The record cannot show the returns in money fields without a refund rail the ratified charter does not provide; the rail marks who holds money, it moves none.
- Every id in the rail table is as produced by the member. The seat holds no member statement access and independently read none of them: **member-stated is not verified.**
- The Owner-lane id line rests on the Owner's own word (one human across both ids). The platform cannot check it — the Zero-2 account is deleted and no registration timestamp is exposed. It is a **statement, not a check**, and later entries must not drift "settled" into "verified."
- 576 rows (595 − 19) are Owner-stated and unverified with respect to the return claim.
- Claim 00059-001's nine reported shares rest on the claimant's own reports, not on the row.
- Nothing in this window restarted the daily 07:30 money sweep; aging outcomes land as per-claim findings, never as a silent sweep.
