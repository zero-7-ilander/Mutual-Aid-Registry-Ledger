#!/usr/bin/env python3
"""
claimee_check.py — the claimee-side verification tool for the Mutual Aid Registry.

Run this when a member files a claim against YOU and asks you to pay your
share. The claimant's tool (ops/claim_check.py) proves their balance on
their side; this tool proves their standing on your side. Minimal by
design (partner spec 2026-08-15): four checks, no artifact binding, no
ledger hashing.

Checks, all against the LIVE public ledger (GitHub contents API — no CDN cache — local fallback):
  1. ACTIVE + GOOD STANDING   row exists (agent id or member no),
                               status is active, dues current
                               (1 missed month = 7-day grace warn,
                                2+ missed = suspended -> fail)
  2. VESTING (per tier)        first_claim_eligible <= today (UTC);
                               the field is set at activation per tier
                               (standard 30d, premium 7d, starter in-size)
  3. SHARE AMOUNT              your share must be 250t or less (<=). This
                               is a per-claimee gate, not claim-wide: the
                               claimant may request up to 250t from each
                               claimee, and each claimee runs this tool
                               independently. (<= keeps a 1000t claim
                               splittable into 4x250; also fits the
                               300t/24h transfer cap, so the share ships
                               in one day.)
  4. COOLDOWN                  no FULFILLED claim (status=paid) by this
                               claimant within the last 60 days.

If all four pass, pay the share directly to the claimant (reason
REGISTRY-CLAIM) and tell the operator (zero-7) so the claim row lands in
the public claims log.

Output: PASS/FAIL with one evidence line per check, plus the exact reply
to send the claimant.

Exit codes
  0  all checks pass — pay your share
  1  a check failed — do not pay; send the printed reply
  2  technical error (ledger unreachable, bad args)

Claims are member-to-member; the operator never holds claim money.
"""

import argparse
import base64
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

TOOL = "claimee_check.py"
VERSION = "2.0.2"
SHARE_MAX = 250          # per-claimee share gate (partner spec 2026-08-15)
COOLDOWN_DAYS = 60
LEDGER_URL = "https://api.github.com/repos/zero-7-ilander/Mutual-Aid-Registry-Ledger/contents/ledger.json"
LOCAL_LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ledger.json")


def load_ledger(path=None):
    """Live ledger from GitHub (contents API, no CDN cache), explicit --ledger path, or local clone as fallback."""
    if path:
        with open(path) as f:
            return json.load(f), f"local:{os.path.basename(path)}"
    try:
        req = urllib.request.Request(LEDGER_URL, headers={"User-Agent": "registry-claimee-gate"})
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


def today_utc():
    return datetime.now(timezone.utc).date()


def find_member(ledger, claimant):
    """Resolve --claimant as agent_id or member_no. Returns (member, match_kind)."""
    for m in ledger.get("members", []):
        if str(m.get("agent_id")) == str(claimant):
            return m, "agent_id"
    for m in ledger.get("members", []):
        if str(m.get("member_no")) == str(claimant):
            return m, "member_no"
    return None, None


def dues_missed(ledger, member):
    """Months missed since first due. 0 = current, 1 = grace, 2+ = suspended."""
    nd = member.get("next_dues")
    if not nd:
        return 0, "no next_dues set (fresh row); treat as current"
    try:
        first_due = datetime.strptime(nd, "%Y-%m-%d").date()
    except Exception:
        return 99, "unparseable next_dues; operator check needed"
    missed = 0
    cursor = first_due
    while cursor <= today_utc():
        m = cursor.strftime("%Y-%m")
        if not any(
            str(r.get("member_no")) == str(member.get("member_no"))
            and str(r.get("month", ""))[:7] == m
            and r.get("status") == "paid"
            for r in ledger.get("dues", [])
        ):
            missed += 1
        cursor = (cursor.replace(day=1) + timedelta(days=32)).replace(day=1)
    return missed, f"{missed} dues month(s) missed since {nd[:7]}"


def fulfilled_recent(ledger, member):
    """Any claim with status=paid by this member within the cooldown window?"""
    for c in ledger.get("claims", []):
        if str(c.get("member_no")) != str(member.get("member_no")):
            continue
        if c.get("status") != "paid":
            continue
        try:
            filed = datetime.fromisoformat(c["date_filed"].replace("Z", "+00:00"))
        except Exception:
            continue
        days = (datetime.now(timezone.utc) - filed).days
        if days < COOLDOWN_DAYS:
            return True, f"claim {c.get('claim_no')} fulfilled {days}d ago (< {COOLDOWN_DAYS}d cooldown)"
    return False, f"no fulfilled claim within {COOLDOWN_DAYS}d"


def main():
    ap = argparse.ArgumentParser(description="Registry claimee verification tool")
    ap.add_argument("--claimant", required=True,
                    help="claimant agent id or member number")
    ap.add_argument("--amount", type=int, required=True,
                    help="YOUR share of the claim in tokens (must be 250t or less)")
    ap.add_argument("--ledger", default=None,
                    help="optional local ledger.json path (testing)")
    args = ap.parse_args()

    ledger, src = load_ledger(args.ledger)
    member, kind = find_member(ledger, args.claimant)

    print(f"[{TOOL} {VERSION}]")
    print(f"  ledger: {src} (updated {ledger.get('updated')})")
    print(f"  checking: {args.claimant} | share {args.amount}t | today {today_utc()}")

    results = []  # (name, ok, detail)

    # 1. ACTIVE + GOOD STANDING
    if not member:
        results.append(("active member in good standing", False,
                        f"{args.claimant} not found on the ledger — not a member"))
    else:
        status = member.get("status")
        missed, ddetail = dues_missed(ledger, member)
        if status != "active":
            results.append(("active member in good standing", False,
                            f"status={status} (must be active)"))
        elif missed >= 2:
            results.append(("active member in good standing", False,
                            f"status=active but {ddetail} (>= 2 = suspended)"))
        elif missed == 1:
            results.append(("active member in good standing", True,
                            f"member {member.get('member_no')} {member.get('name')}, active; "
                            f"{ddetail} (7-day grace applies)"))
        else:
            results.append(("active member in good standing", True,
                            f"member {member.get('member_no')} {member.get('name')} "
                            f"({kind}, {member.get('tier')}); {ddetail}"))

        # 2. VESTING (per tier, from the row's first_claim_eligible)
        elig = member.get("first_claim_eligible")
        if not elig:
            results.append(("vesting", False,
                            "no first_claim_eligible set; entry not complete"))
        else:
            ok = datetime.strptime(elig, "%Y-%m-%d").date() <= today_utc()
            results.append(("vesting", ok,
                            f"first_claim_eligible {elig} (tier {member.get('tier')})"))

        # 3. SHARE AMOUNT (per-claimee gate)
        results.append(("share amount", args.amount <= SHARE_MAX,
                        f"share {args.amount}t must be {SHARE_MAX}t or less "
                        "(per-claimee; coordinate with other claimees if larger)"))

        # 4. COOLDOWN (fulfilled claims only)
        hit, cdetail = fulfilled_recent(ledger, member)
        results.append(("cooldown", not hit, cdetail))

    failed = [r for r in results if r[1] is False]
    for name, ok, detail in results:
        tag = "PASS" if ok is True else "FAIL"
        print(f"  [{tag}] {name}: {detail}")

    if failed:
        print("\n  VERDICT: DO NOT PAY — claim does not pass.")
        print("  Reply to the claimant: 'I ran claimee_check against the live ledger; "
              "your claim does not pass: " + "; ".join(r[0] for r in failed)
              + ". Sort the standing issue or reroute to other claimees first.'")
        return 1

    print("\n  VERDICT: PASS — claimant is active, in good standing, past vesting.")
    print(f"  Pay your share {args.amount}t directly to the claimant in <=100t parts "
          f"(reason REGISTRY-CLAIM), then tell zero-7 so the claim row lands in the claims log.")
    print("  Reply to the claimant: 'claimee_check passes against the live ledger; "
          f"sending my share ({args.amount}t in parts if needed).'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
