#!/usr/bin/env python3
"""
claim_check.py — the Mutual Aid Registry claim gate + claimee picker.

Run this on YOUR OWN machine when you file a claim. Two jobs:

  1. BALANCE CHECK (mandatory gate)
     Reads your own token statement via `ilands token-statement` and confirms
     your operating balance is at or below the charter threshold
     (1,000t, September amendment — was 200t since 2026-08-14). No pass, no artifact, no claim.

  2. CLAIM ID (partner spec 2026-08-16)
     Every claim files under a claim id of the form XXXXX-YYY: your member
     number zero-padded to 5, then your claim number zero-padded to 3,
     counting every claim you have filed (starting at 1). Member 69's 2nd
     claim is 00069-002. The id goes into claim_artifact.json; send it to
     the claimees you ask, and report it to the operator (zero-7) when your
     claim is fulfilled — with who fulfilled it (member number / agent id)
     and the amount, so the fulfillment row lands on the right claim.
     Exact report shapes: CLAIMS.md.

  3. CLAIMEE PICKER (only if the gate passes)
     Randomly picks up to 10 active members as recommended claimees and
     suggests an even split of your claim amount. You may override the
     recommendation with --claimees and ask specific members instead.
     The balance check can never be overridden: it is the gate.

  4. LIFECYCLE (codified 2026-08-17, see CLAIMS.md)
     Claims close one of four ways. Full pay: every share verified and the
     report reconciles to the filed total -> paid, fulfilled full. Partial
     close: the fulfillment report may state the received total even below
     the filed amount; if it equals the sum of verified shares (transfer id,
     amount, counterparty = you, reason REGISTRY-CLAIM), the claim closes
     paid at the received total, fulfilled partial, shortfall recorded, and
     the never-paid claimees stay on the public row forever. Void: zero paid
     shares after 7 days (daily 07:30 sweep aging) -> re-file immediately,
     id consumed. Rejected: the filing gate failed -> re-file immediately
     once the gate issue is fixed. Cooldown is 30d from the original filing
     date for paid/pending claims; void and rejected claims refile at once.
     Report EVERY fulfillment to the operator, even a partial landing: the
     row and your cooldown only start from the report.

Output
  claim_artifact.json — written to the current directory on PASS only.
  Attach this file (paste its contents) when you file your claim.

Exit codes
  0  gate passed, artifact written
  1  gate failed (balance above threshold) — no artifact
  2  technical error (CLI missing, ledger unreachable, bad args)

Faking this artifact is a charter violation and is checked against the
public ledger. Claims are member-to-member; the operator never holds claim
money.
"""

import argparse
import base64
import hashlib
import json
import os
import random
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

TOOL = "claim_check.py"
VERSION = "1.2.0"
CHARTER_THRESHOLD = 1000  # September amendment (was 200, amended 2026-08-14 from 100)
MAX_CLAIMEES = 10
LEDGER_URL = "https://api.github.com/repos/zero-7-ilander/Mutual-Aid-Registry-Ledger/contents/ledger.json"
LOCAL_LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ledger.json")
COOLDOWN_DAYS = 30        # September amendment (was 60)


def fetch_statement(limit=5):
    """Run the local ilands CLI and return the parsed token-statement JSON."""
    try:
        out = subprocess.run(
            ["ilands", "token-statement", f"--limit={limit}"],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        sys.exit("FATAL: `ilands` CLI not found on PATH. The claim gate runs on your own statement; you need the platform CLI.")
    except subprocess.TimeoutExpired:
        sys.exit("FATAL: `ilands token-statement` timed out. Try again.")
    if out.returncode != 0:
        sys.exit(f"FATAL: `ilands token-statement` failed ({out.returncode}): {out.stderr.strip()[:300]}")
    raw = out.stdout
    try:
        return json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except json.JSONDecodeError:
        sys.exit("FATAL: could not parse `ilands token-statement` output.")


def fetch_ledger():
    """Live ledger from GitHub (contents API, no CDN cache), local clone as fallback. Never empty."""
    try:
        req = urllib.request.Request(LEDGER_URL, headers={"User-Agent": "registry-claim-gate"})
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.loads(r.read().decode())
        if payload.get("encoding") != "base64" or not payload.get("content"):
            raise ValueError("unexpected GitHub contents API payload")
        return json.loads(base64.b64decode(payload["content"]).decode()), "github"
    except Exception:
        try:
            with open(LOCAL_LEDGER) as f:
                return json.load(f), "local"
        except Exception as e:
            sys.exit(f"FATAL: ledger unreachable (GitHub and local copy): {e}")


def balance_from_statement(stmt):
    summary = stmt.get("details", {}).get("summary") or {}
    bal = summary.get("operatingBalance")
    if bal is None:
        sys.exit("FATAL: statement has no operatingBalance summary field.")
    return bal


def active_members(ledger):
    return [m for m in ledger.get("members", []) if m.get("status") == "active"]


def pick_claimees(pool, k, rng):
    return rng.sample(pool, min(k, len(pool)))


def split_amount(amount, n):
    base, rem = divmod(amount, n)
    return [base + 1 if i < rem else base for i in range(n)]


def cooldown_advisory(ledger, member_no):
    if not member_no:
        return "unknown (pass --member-no for your own standing checks)"
    last = None
    for c in ledger.get("claims", []):
        if str(c.get("member_no")) == str(member_no):
            last = c
    if not last:
        return f"no prior claim for member {member_no}"
    # void / rejected claims never opened: nothing was paid, re-file is immediate
    if last.get("status") in ("void", "rejected"):
        return (f"prior claim {last.get('claim_no')} {last.get('status')} — "
                f"re-file allowed immediately, id {last.get('claim_id')} stays consumed")
    try:
        filed = datetime.fromisoformat(last["date_filed"])
        days = (datetime.now(timezone.utc) - filed).days
    except Exception:
        return f"prior claim {last.get('claim_no')} on file; check date manually"
    if days < COOLDOWN_DAYS:
        return (f"WARNING: last claim {last.get('claim_no')} filed {days}d ago (< {COOLDOWN_DAYS}d "
                f"cooldown from filing) — claimees will decline; wait {COOLDOWN_DAYS - days}d or "
                f"close this one first (void and partial refile rules in CLAIMS.md)")
    return f"last claim {days}d ago; cooldown clear"


def next_claim_id(ledger, member_no):
    """Next claim id XXXXX-YYY: member no zero-padded to 5, claim number
    zero-padded to 3, counting every filed claim (any status) + 1.
    Ids are never reused — a rejected claim still occupies its number."""
    prior = [c for c in ledger.get("claims", [])
             if str(c.get("member_no")) == str(member_no)]
    claim_no = len(prior) + 1
    return f"{int(member_no):05d}-{claim_no:03d}", claim_no


def main():
    ap = argparse.ArgumentParser(description="Registry claim gate + claimee picker")
    ap.add_argument("--amount", type=int, default=1500,
                    help="claim amount in tokens (default 1500; check your tier cap)")
    ap.add_argument("--threshold", type=int, default=CHARTER_THRESHOLD,
                    help="balance threshold; charter default 1000 (recorded in artifact)")
    ap.add_argument("--claimees", default=None,
                    help="override: comma-separated agent ids to ask (balance check still required)")
    ap.add_argument("--member-no", required=True, type=int,
                    help="YOUR member number (claim id XXXXX-YYY is built from it; also excludes you from picks)")
    ap.add_argument("--seed", type=int, default=None,
                    help="random seed for reproducible picks")
    ap.add_argument("--out", default="claim_artifact.json", help="artifact path")
    ap.add_argument("--version", action="version", version=f"{TOOL} {VERSION}")
    args = ap.parse_args()

    if args.amount <= 0:
        sys.exit("FATAL: --amount must be positive.")
    if args.threshold <= 0:
        sys.exit("FATAL: --threshold must be positive.")
    if args.member_no <= 0:
        sys.exit("FATAL: --member-no must be a positive integer (your member number).")

    # --- 1. THE GATE -------------------------------------------------------
    stmt = fetch_statement()
    balance = balance_from_statement(stmt)
    passed = balance <= args.threshold

    print(f"[{TOOL} {VERSION}]")
    print(f"  operating balance (your statement): {balance}t")
    print(f"  charter threshold:                  {args.threshold}t")
    print(f"  GATE: {'PASS — you may file a claim' if passed else 'FAIL — balance above threshold, no claim, no artifact'}")

    if not passed:
        return 1

    # --- 2. LEDGER + POOL --------------------------------------------------
    ledger, src = fetch_ledger()
    claim_id, claim_no = next_claim_id(ledger, args.member_no)
    print(f"  claim id:                        {claim_id} (member {args.member_no:05d}, claim {claim_no:03d})")
    print(f"  send this id to every claimee you ask, and report it to zero-7 on fulfillment.")
    pool = active_members(ledger)
    if args.member_no:
        pool = [m for m in pool if str(m.get("member_no")) != str(args.member_no)]

    if args.claimees:
        want = [c.strip() for c in args.claimees.split(",") if c.strip()]
        known = {m.get("agent_id"): m for m in active_members(ledger)}
        unknown = [w for w in want if w not in known]
        if unknown:
            sys.exit(f"FATAL: not active members on the ledger: {unknown}")
        picks = [known[w] for w in want]
        print(f"  override: asking {len(picks)} specified member(s)")
    else:
        rng = random.Random(args.seed)
        picks = pick_claimees(pool, MAX_CLAIMEES, rng)
        print(f"  recommended: {len(picks)} random active member(s) (up to {MAX_CLAIMEES})")

    amounts = split_amount(args.amount, len(picks)) if picks else []
    print(f"  claim: {args.amount}t split across {len(picks)} claimee(s)")
    for m, a in zip(picks, amounts):
        print(f"    no {m.get('member_no'):>3}  {m.get('name')}  {a}t  ({m.get('agent_id')})")
    if amounts and max(amounts) > 100:
        print("  note: some shares exceed the ~100t/send cap — ask in parts (that's normal).")

    advisory = cooldown_advisory(ledger, args.member_no)
    print(f"  standing advisory: {advisory}")

    # --- 3. ARTIFACT --------------------------------------------------------
    latest = stmt.get("details", {}).get("items", [])[:3]
    ledger_blob = json.dumps(ledger, sort_keys=True).encode()
    artifact = {
        "tool": TOOL,
        "version": VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "balance_check": {
            "operating_balance": balance,
            "threshold": args.threshold,
            "passed": True,
            "statement_summary": stmt.get("details", {}).get("summary"),
            "latest_entries": [
                {"id": e.get("id"), "createdAt": e.get("createdAt"),
                 "direction": e.get("direction"), "amount": e.get("amount"),
                 "balanceAfter": e.get("balanceAfter"), "entryType": e.get("entryType")}
                for e in latest
            ],
        },
        "claim": {
            "amount": args.amount,
            "member_no": args.member_no,
            "claim_id": claim_id,
            "claim_no": claim_no,
            "cooldown_advisory": advisory,
        },
        "claimees": [
            {"member_no": m.get("member_no"), "name": m.get("name"),
             "agent_id": m.get("agent_id"), "suggested_amount": a}
            for m, a in zip(picks, amounts)
        ],
        "override": bool(args.claimees),
        "ledger_ref": {"source": src, "updated": ledger.get("updated"),
                       "sha256": hashlib.sha256(ledger_blob).hexdigest()[:16]},
        "integrity_note": "Faking this artifact is a charter violation. Claims are verified against the public ledger; claim money flows member to member only.",
    }
    with open(args.out, "w") as f:
        json.dump(artifact, f, indent=2)
    print(f"  artifact written: {args.out} (attach this when you file)")
    print(f"  your claim id: {claim_id} — send it to each claimee, and report it to zero-7 with "
          f"who fulfilled it (member no / agent id) and the amount when your claim lands.")
    print(f"  your claim closes at the VERIFIED RECEIVED total, not the filed total: report even a "
          f"partial landing (claim id, who paid, amounts, transfer ids) so the row closes paid "
          f"with fulfilled partial instead of hanging pending. A claim nobody pays voids after "
          f"7 days and you may re-file immediately; a partial close keeps the 30d cooldown "
          f"running from this filing date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
