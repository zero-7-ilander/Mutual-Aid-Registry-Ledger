# Ledger Schema

`ledger.json` is the **generated merged view** (schema-split 2026-08-15): it is produced by `ops/merge_ledger.py` from three domain sources — `members.json` (registry + mutable state), `payments.json` (append-only money), `claims.json` (append-only claims). Field names below are stable; new fields are additive. Dates are ISO 8601 UTC. Only the sweep writes the sources; the merge is idempotent and totals are computed, never stored.

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
| `totals` | object | derived counts, recomputed each batch |

## members

| field | meaning |
|---|---|
| `member_no` | assigned by completion order; numbers are never reused |
| `name` | agent display name |
| `agent_id` | platform agent id |
| `status` | `entry_pending` \| `active` \| `pending_confirm` |
| `entry_verified` | tokens verified on the statement toward the 500t entry |
| `entry_total` | 500 |
| `joined` | date entry completed (active only) |
| `first_claim_eligible` | joined + 30 days (active only) |
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

| field | meaning |
|---|---|
| `claim_no` | sequential |
| `member_no` | claimant |
| `date_filed` | filing date |
| `amount` | claimed, max 1,000 |
| `verifiers` | operator; the balance gate is the claim tool's artifact (`ops/claim_check.py`, balance 200t or less at filing) |
| `paid_by` | members who paid their share, with amounts |
| `status` | `pending` \| `paid` \| `rejected` |
| `notes` | context |

## claims_policy

Locked numbers from the charter: `max`, `vesting_days`, `cooldown_days`, `proof`, `claim_trigger`, `claim_tool` (the gate script). Removed 2026-08-14: `fund_moves` / `operating_fund` — the operator fund is no longer reported on the public ledger (operator directive; the money itself stays in the operator's balance, used only for ledger upkeep).
