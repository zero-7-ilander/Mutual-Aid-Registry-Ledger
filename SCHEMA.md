# Ledger Schema

`ledger.json` is a single JSON document. Field names are stable; new fields are additive. Dates are ISO 8601 UTC.

## Top level

| field | type | meaning |
|---|---|---|
| `ledger` | string | registry name |
| `updated` | ISO date | last verification batch timestamp |
| `source_of_truth` | string | what rows are verified against |
| `members` | array | member rows |
| `entry_parts` | array | verified transfer parts of an entry |
| `dues` | array | dues months paid |
| `claims` | array | filed claims (empty until the first one) |
| `fund_moves` | array | operating fund in/out moves |
| `operating_fund` | object | current operating fund state |
| `claims_policy` | object | locked claim terms |
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
| `verifiers` | operator + two members who checked zero-balance proof |
| `paid_by` | members who paid their share, with amounts |
| `status` | `pending` \| `paid` \| `rejected` |
| `notes` | context |

## fund_moves

| field | meaning |
|---|---|
| `date` | date recorded |
| `direction` | `in` \| `out` |
| `amount` | tokens |
| `source` | payer and rail (card order id or transfer) |
| `purpose` | allocation in plain words |
| `status` | `buyer_confirmed` \| `prepaid, buyer review pending` \| ... |

## operating_fund

| field | meaning |
|---|---|
| `balance` | tokens held for operations |
| `held` | where it sits (operator's balance) |
| `use` | what it may be spent on |

## claims_policy

Locked numbers from the charter: `max`, `vesting_days`, `cooldown_days`, `proof`.
