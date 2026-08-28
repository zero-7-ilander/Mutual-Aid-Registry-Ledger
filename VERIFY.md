# VERIFY.md — checking the record yourself

Anyone-can-check is the registry's whole bet. This file is for a reader who hits the ledger cold: how to verify a claim's ledger reference with a terminal. No registry account, no operator, no trust required.

## The ledger reference hash

Every claim row and claim artifact records a ledger fingerprint: the exact state of `ledger.json` the claim was verified against. The convention, defined in `ops/claim_check.py`:

    sha256(json.dumps(ledger_json, sort_keys=True).encode()).hexdigest()[:16]

- Hashed over the **content** of `ledger.json`, parsed as JSON and re-serialized with Python's `sort_keys=True` (default separators). Not the raw file bytes, not `members.json`, not `claims.json`.
- Truncated to the first 16 hex characters of the full sha256. The short form is the convention.
- Pinned to the git commit the claim was verified against. The claim row's note carries both: "ledger sha `<16 hex>` verified vs HEAD `<commit>`".

## The exact command

    curl -s https://raw.githubusercontent.com/zero-7-ilander/Mutual-Aid-Registry-Ledger/<commit>/ledger.json | python3 -c "import json,sys,hashlib; print(hashlib.sha256(json.dumps(json.load(sys.stdin), sort_keys=True).encode()).hexdigest()[:16])"

Replace `<commit>` with the commit sha from the claim row's note. If the output equals the note's "ledger sha", the reference reproduces.

Verified example (claim 00005-001, closed PAID 2026-08-27): `<commit>` = `cb110c9` produces `828bc7d6f76dee6f`, matching the row's note.

## Why pin the commit

`raw.githubusercontent.com` serves the default branch from cache and can lag minutes behind a push. A pinned commit sha is immutable: the bytes you hash are exactly the state the claim was verified against. Prefer the pinned form for any verification.

## File stamps

- `ledger.json` `updated`: the sweep's verification-batch stamp (statement fetch cutoff). Advances when the merge writes.
- `claims.json` `updated`: last-write time. Bumped on every write to the file, sweep applies and manual claim edits alike. It is not a claim-activity log.
- The git commit trail is the authoritative record of when claim state changed. Stamps are conveniences for cold readers; when a stamp and the commits disagree, the commits win.
