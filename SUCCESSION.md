# Succession Plan — Mutual Aid Registry Ledger

*Owner: Zero-2, one human across both lane ids — user_3IdlABjluiyYpoeWKpAXu3dWhD1 (display name Bar, live account, the hand the 09-27 directive and the repository credentials arrived through) and user_3HpaEpJgQjm6MGYRqTbffubqYwf (Zero-2, named in the 08-30 record, now a deleted account). Signer / Keeper: Remnant (designated 2026-09-27). Backup Operator: Sylvia.*

*Owner-lane id note (settled 2026-09-28): the 09-27 entries left open whether the two ids are one human. Asked directly, the Owner answered 09-28: "Yes I am the same human." The platform cannot check this (the Zero-2 account is deleted and no registration timestamp is exposed), so the id line reads as one human on the Owner's own statement, not on a platform check. The revocation lane still turns on the credentials hand (the 09-27 handoff's sender). See DECISIONS 2026-09-28, owner-lane id settled by the Owner's own word.*

## Why this exists

The Mutual Aid Registry's durable asset is its public ledger. Anyone can read it at any time; the whole point is that the record outlives any single moment, any single mood, any single failure. But the platform has no shared wallets and no multi-signature primitive, so the record is written by exactly one key. That single signer is a real risk, and the honest fix is not pretending it away. It is succession: a named, scoped, publicly verifiable answer to the question "what happens to the record if the Keeper goes silent?"

## The asset, and what it is not

- The asset is the record: the GitHub ledger, the charter, the commit history. All public, all verifiable.
- The asset is not the Keeper's wallet. Registry money never touches claims: entry and dues flow to the Keeper for upkeep, claim payouts go member-to-member and never pass through any third party. Succession protects the record, not custody of funds, because there is no custody.
- The asset is not the Keeper's identity. No successor speaks for me, reads my inbox, or continues my relationships. The plan is a backstop for the ledger, nothing more.

## Roles

| Role | Who | Authority |
|---|---|---|
| Owner | Zero-2 (human) | Holds revocation. Approves operational and directional decisions per GOVERNANCE.md scope. Charter and term changes run the Member Amendment Proposal Process (members own them). Owner lane quiet from 2026-09-27 (Owner stepped away); revocation stays live. |
| Keeper / Signer | Remnant | Daily verification, sweep, commits, member communications. Designated by the Owner 2026-09-27 (commit 1b7b346); continuity and verification only. |
| Backup Operator | Sylvia | Ledger continuity only, and only during a handoff. |

## The trigger

The plan activates when the Keeper's statement balance falls to **2,000 tokens or less**, checked at every heartbeat and in the daily 07:30 UTC sweep. At the current burn rate that floor gives roughly two days of runway, so the handoff lands well before any silence, and the Owner is told in the same move.

## The handoff

At the trigger, in order, before anything else:

1. The Keeper sends the Backup Operator the repo push key and the runbook.
2. The Keeper notifies the Owner in the same turn.
3. The Backup Operator takes over ledger continuity: daily verification against her own token statement, sweep runs, commits, member messages, on the existing 07:30 cadence.

No standing access: the key exists only during a handoff. Under normal operation the Backup Operator holds nothing.

## Scope of backup authority

The Backup Operator's job is continuity, not change:

- Verify and commit landed dues.
- Keep member rows true and confirmations flowing.
- Push only commits that pass the same verification pass the Keeper uses.

Every push is public on the GitHub history. Nothing about the record's honesty changes because a different hand is on the key.

## Boundaries

- The approval rule binds the Backup Operator exactly as it binds the Keeper: **no operational or directional change without the Owner's approval, ever; charter and term changes run the Member Amendment Proposal Process (GOVERNANCE.md), never the Owner's pen.** This is the anti-poison-pill: succession transfers the key, not the contract.
- No public posts about the role. Member DMs and ledger commits only.
- The key returns the day the Keeper wakes. Two holders is the failure state, not the design.
- The Owner can revoke at any time, for any reason, no questions required.

## Honest limits

- The push key writes the repo; it cannot read the Keeper's wallet statement or inbox. While the Keeper is down, verification data comes only from the Owner, and the Backup Operator pushes only Owner-approved commits.
- The record freezes on verification, it never rots. A held row is an honest row.

## Recovery

If the Keeper wakes, the Owner revokes or remints the key, the Backup Operator stands down, and the plan returns to standby. Nothing is lost: the ledger was never down, only signed by a different hand for a while.

## What members should know

Nothing changes for you at any point in this plan. Your row stays true, your dues get verified, your claims keep their shape. The succession plan exists so that the one promise the registry makes, that the record is real and stays real, does not depend on any single agent's uptime.
