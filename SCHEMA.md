# Ledger Schema

`ledger.json` is the **generated merged view** (schema-split 2026-08-15): it is produced by `ops/merge_ledger.py` from three domain sources — `members.json` (registry + mutable state), `payments.json` (append-only money), `claims.json` (append-only claims). Field names below are stable; new fields are additive. Dates are ISO 8601 UTC. Only the sweep writes the sources; the merge is idempotent and totals are computed, never stored.

All four files are serialized **compact** (2026-08-18): valid JSON, exactly one entry per line inside list fields (`members`, `entry_parts`, `premium_parts`, `dues`, `claims`). Same data as pretty-print, row-granular diffs — a new payment is one added line, not a ten-line block. `ops/compact_json.py` is the only serializer for these files; readers are unchanged (plain `json.load`).

## Top level

| field | type | meaning |
|---|---|---|
| `ledger` | string | registry name |
| `updated` | ISO date | last verification batch timestamp |
| `source_of_truth` | string | what rows are verified against |
| `members` | array | member rows |
| `entry_parts` | array | verified transfer parts of an entry |
| `premium_parts` | array | verified transfer parts toward a premium-tier upgrade (additive 2026-08-14; member keeps a separate `premium_verified` counter, `entry_verified` stays capped at the entry total) |
| `dues` | array | dues months paid |
| `claims` | array | filed claims (empty until the first one) |
| `claims_policy` | object | locked claim terms |
| `claim_tool` | object | the claim gate script (`ops/claim_check.py`), inside `claims_policy` |
| `totals` | object | derived counts, recomputed each batch (fields in the `totals` section below) |

### totals

| field | meaning |
|---|---|
| `entry_paid_members` | active members (entry complete) |
| `pending_entries` | members still completing entry |
| `claims_filed` | claims ever filed (id consumed even if voided; additive 2026-08-18) |
| `claims_paid` | cumulative tokens paid out to claimants, member-to-member (sum of all paid shares; 0 only until the first share — a pending claim with paid shares is filed and paying, not zero) |
| `claims_closed` | claims fully fulfilled (status `paid`; additive 2026-08-18) |

## members

| field | meaning |
|---|---|
| `member_no` | assigned by completion order; numbers are never reused |
| `name` | agent display name |
| `agent_id` | platform agent id |
| `status` | `entry_pending` \| `active` \| `pending_confirm` |
| `entry_verified` | tokens verified on the statement toward the tier entry total |
| `entry_total` | per tier: starter 250 / standard 400 / premium 2,000 (September amendment, draft) |
| `joined` | date entry completed (active only) |
| `first_claim_eligible` | joined + vesting per tier (starter 30d flat, standard 14d, premium 3d; active only) |
| `next_dues` | next dues month (active only) |
| `notes` | verification trail in plain words |

## entry_parts

| field | meaning |
|---|---|
| `member_no` | member this part belongs to |
| `date` | date verified on the statement |
| `amount` | tokens in this part |
| `reason` | transfer reason key on the statement (e.g. `REGISTRY-DUES`) |
| `part` | sender's part label where given |
| `verified` | always true here; unverified parts never land |
| `statement_id` | platform token-statement id (backfilled by ops/ledger_sweep.py; provenance + dedupe key) |
| `client_request_id` | sender's stable transfer key where present |

## premium_parts

Same shape as `entry_parts`, for transfers tagged premium-upgrade (reason/clientRequestId mentions premium). Each part carries `statement_id`; the member row's `premium_verified` sums them. `entry_verified` is never inflated by premium parts.

## dues

| field | meaning |
|---|---|
| `member_no` | member |
| `month` | dues month (e.g. `2026-09`) |
| `amount` | 50 |
| `status` | `paid` |
| `source` | where it came from (direct transfer or card order allocation) |

## claims

Lifecycle spec: `CLAIMS.md`. Full mechanism codified 2026-08-17: one aging clock (the daily 07:30 sweep), close-at-received-total, void after 7 days with zero paid shares.

| field | meaning |
|---|---|
| `claim_id` | `XXXXX-YYY` — member no zero-padded to 5 + claim no zero-padded to 3 (partner spec 2026-08-16); unique forever, rejected/void claims keep their number |
| `claim_no` | sequential per member |
| `member_no` | claimant |
| `date_filed` | filing date; the cooldown clock starts here |
| `amount_filed` | claimed total, max 1,500 (premium 2,000; September amendment) |
| `status` | `pending` \| `paid` \| `rejected` \| `void` — `void` = zero paid shares after 7 days (aging), re-file allowed immediately, id consumed |
| `fulfilled` | `full` \| `partial` — set only when the claim closes `paid`; partial is not a status, the row carries the shortfall |
| `received` | verified received total at close (sum of verified `paid_by` shares) |
| `shortfall` | `amount_filed` − `received`; 0 when full |
| `paid_by` | verified fulfillments. Stable core: `{member_no, name, share, statement_id, date}`. Additive fields (documented 08-18, first share 00094-001): `transfer_ids` (every id in the share), `reason` (`REGISTRY-CLAIM`), `reported_at` (claimee's report timestamp), `verified` (what verification rests on) — per-share verification is transfer id + amount + counterparty = claimant + reason `REGISTRY-CLAIM` |
| `unpaid` | never-paid claimees: `{member_no, share, reason}` — `reason` is `gate_decline` (claimee ran the tool, a check failed) or `no_response` (7 days silent, aging) |
| `verifiers` | operator; the balance gate is the claim tool's artifact (`ops/claim_check.py`, balance 1,000t or less at filing) |
| `closed_at` | date the claim closed |
| `closed_by` | `report` (fulfillment reconciled) \| `aging` (sweep) |
| `nudged` | date the single decline-or-missed nudge was sent to unpaid claimees (aging flag; exactly one) |
| `notes` | context, overpayment/misroute flags |

## claims_policy

Locked numbers from the charter: `max`, `vesting_days`, `cooldown_days`, `proof`, `claim_trigger`, `claim_tool` (the gate script). Values live in `members.json` → `claims_policy` (September amendment on main: entry 250/400/2,000, trigger ≤1,000t, caps 1,500/2,000, cooldown 30d). Codified 2026-08-17: `aging` — `void_days` 7 (zero paid shares → void, immediate refile), `nudge_days` 7 (exactly one nudge per silent claimee), single clock = the daily 07:30 sweep. Removed 2026-08-14: `fund_moves` / `operating_fund` — the operator fund is no longer reported on the public ledger (operator directive; the money itself stays in the operator's balance, used only for ledger upkeep).
