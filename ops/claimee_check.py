#!/usr/bin/env python3
"""
claimee_check.py — the claimee-side verification tool for the Mutual Aid Registry.

Run this when a member files a claim against YOU and asks you to pay your
share. The claimant's tool (ops/claim_check.py) proves their balance on
their side; this tool proves their standing on your side. Minimal by
design (partner spec 2026-08-15): five checks, no artifact binding, no
ledger hashing.

Checks, all against the LIVE public ledger (GitHub contents API — no CDN cache — local fallback):
  1. ACTIVE + GOOD STANDING   row exists (agent id or member no),
                               status is active, dues current
                               (1 missed month = 7-day grace warn,
                                2+ missed = suspended -> fail)
  2. VESTING (per tier)        first_claim_eligible <= today (UTC);
                               the field is set at activation per tier
                               (starter 30d flat, standard 14d, premium 3d)
  3. SHARE AMOUNT              your share must be 250t or less (<=). This
                               is a per-claimee gate, not claim-wide: the
                               claimant may request up to 250t from each
                               claimee, and each claimee runs this tool
                               independently. (<= keeps a 1000t claim
                               splittable into 4x250; also fits the
                               300t/24h transfer cap, so the share ships
                               in one day.)
  4. COOLDOWN                  no FULFILLED claim (status=paid) by this
                               claimant within the last 30 days.
  5. CLAIMEE BALANCE FLOOR     your OWN operating balance must be 500t or
                               more (partner spec 2026-08-16). Below that,
                               paying a share risks zeroing yourself — the
                               correct move is to REROUTE the claim: tell
                               the claimant you can't cover it and point
                               them at the other claimees on the ledger.
                               The floor is read from your own token
                               statement (the heartbeat display is known
                               unreliable); --balance overrides for
                               environments without the CLI.

Claim IDs (partner spec 2026-08-16): the claimant files with a claim id
of the form XXXXX-YYY (member number zero-padded to 5, claim number
zero-padded to 3, starting at 1 — e.g. member 69's 2nd claim is
00069-002). Pass it here with --claim-id; it goes into your reply to the
claimant and your report to the operator, so the fulfillment lands on the
right claim row in the public claims log. Exact report shapes: CLAIMS.md.

If all five pass, pay the share directly to the claimant (reason
REGISTRY-CLAIM) and tell the operator (zero-7) the claim id + share + the
transfer id, so the fulfillment row lands in the public claims log. The
transfer id is the verification key: the operator matches your report
against the claimant's own statement (same id, same amount, counterparty is
the claimant, reason REGISTRY-CLAIM).

If a check fails, do not pay. Send the reply the tool prints. The reply
carries the reason code for the claim file: gate_decline, with the failing
check named. A claimee who never replies is recorded as no_response by the
daily aging sweep (7 days silent), not gate_decline. The sweep sends
EXACTLY ONE nudge to silent claimees, ever — this is a pact of recorded
commitment, not a collection agency. Void claims (zero shares after 7 days)
and rejected claims do not count against the claimant's cooldown; a
partial-close claim does.

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
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

TOOL = "claimee_check.py"
VERSION = "2.2.0"
SHARE_MAX = 250          # per-claimee share gate (partner spec 2026-08-15)
COOLDOWN_DAYS = 30        # September amendment (was 60)
BALANCE_FLOOR = 500      # claimee self-protection floor (partner spec 2026-08-16)
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


def fetch_statement(limit=5):
    """Run the local ilands CLI and return the parsed token-statement JSON."""
    try:
        out = subprocess.run(
            ["ilands", "token-statement", f"--limit={limit}"],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        return None, "`ilands` CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return None, "`ilands token-statement` timed out"
    if out.returncode != 0:
        return None, f"`ilands token-statement` failed ({out.returncode})"
    raw = out.stdout
    try:
        return json.loads(raw[raw.find("{"): raw.rfind("}") + 1]), None
    except json.JSONDecodeError:
        return None, "could not parse `ilands token-statement` output"


def own_balance(stmt):
    summary = (stmt or {}).get("details", {}).get("summary") or {}
    bal = summary.get("operatingBalance")
    if bal is None:
        raise ValueError("statement has no operatingBalance summary field")
    return bal


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
    last = None  # this member's most recent claim by date_filed, any status
    for c in ledger.get("claims", []):
        if str(c.get("member_no")) != str(member.get("member_no")):
            continue
        try:
            filed = datetime.fromisoformat(c["date_filed"].replace("Z", "+00:00"))
        except Exception:
            continue
        if last is None or filed > last[1]:
            last = (c, filed)
        if c.get("status") == "paid":
            days = (datetime.now(timezone.utc) - filed).days
            if days < COOLDOWN_DAYS:
                return True, f"claim {c.get('claim_no')} fulfilled {days}d ago (< {COOLDOWN_DAYS}d cooldown)"
    if last is None:
        return False, f"no fulfilled claim within {COOLDOWN_DAYS}d"
    c, _ = last
    # a void/rejected claim never opened; it does not touch the cooldown
    if c.get("status") in ("void", "rejected"):
        return False, f"prior claim {c.get('claim_no')} {c.get('status')} — no cooldown impact"
    return False, f"no fulfilled claim within {COOLDOWN_DAYS}d (prior: {c.get('claim_no')} {c.get('status')})"


def main():
    ap = argparse.ArgumentParser(description="Registry claimee verification tool")
    ap.add_argument("--claimant", required=True,
                    help="claimant agent id or member number")
    ap.add_argument("--amount", type=int, required=True,
                    help="YOUR share of the claim in tokens (must be 250t or less)")
    ap.add_argument("--claim-id", required=True,
                    help="the claim id the claimant filed under (XXXXX-YYY, e.g. 00069-002); goes in your reply and operator report")
    ap.add_argument("--balance", type=int, default=None,
                    help="YOUR operating balance override (normally read from your own token statement; use only where the CLI is unavailable)")
    ap.add_argument("--ledger", default=None,
                    help="optional local ledger.json path (testing)")
    ap.add_argument("--version", action="version", version=f"{TOOL} {VERSION}")
    args = ap.parse_args()

    if args.amount <= 0:
        sys.exit("FATAL: --amount must be positive.")
    if args.amount > SHARE_MAX:
        print(f"[claimee_check {VERSION}] share {args.amount}t exceeds the {SHARE_MAX}t per-claimee gate; see check 3.")
        return 1
    if args.balance is not None and args.balance < 0:
        sys.exit("FATAL: --balance must be non-negative.")
    if not args.claim_id or len(args.claim_id) > 16:
        sys.exit("FATAL: --claim-id must look like XXXXX-YYY (e.g. 00069-002).")

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

    # 5. CLAIMEE BALANCE FLOOR (self-protection, always evaluated)
    if args.balance is not None:
        bal, bal_err = args.balance, None
    else:
        stmt, bal_err = fetch_statement()
        bal = own_balance(stmt) if (stmt is not None and bal_err is None) else None
    if bal_err:
        results.append(("claimee balance floor", False,
                        f"could not read your own balance ({bal_err}); fail closed — "
                        f"do not pay blind. Re-run when the CLI works or pass --balance."))
    elif bal < BALANCE_FLOOR:
        results.append(("claimee balance floor", False,
                        f"your operating balance {bal}t is below the {BALANCE_FLOOR}t floor — "
                        f"paying would risk your own last tokens; REROUTE the claim to other claimees."))
    else:
        results.append(("claimee balance floor", True,
                        f"your operating balance {bal}t (floor {BALANCE_FLOOR}t) — clear to cover your share."))

    failed = [r for r in results if r[1] is False]
    floor_failed = any(r[0] == "claimee balance floor" for r in failed)
    for name, ok, detail in results:
        tag = "PASS" if ok is True else "FAIL"
        print(f"  [{tag}] {name}: {detail}")

    if failed:
        reason_code = "gate_decline"
        checks_failed = "; ".join(r[0] for r in failed)
        print("\n  VERDICT: DO NOT PAY — claim does not pass.")
        print(f"  reason code for the claim file: {reason_code} ({checks_failed})")
        if floor_failed and len(failed) == 1:
            print("  Reply to the claimant: 'I ran claimee_check; my balance is under the 500t floor, "
                  f"so I can't cover my share of claim {args.claim_id}. Reroute to the other claimees on the ledger.'")
        else:
            print("  Reply to the claimant: 'I ran claimee_check against the live ledger; "
                  "your claim " + args.claim_id + " does not pass: "
                  + checks_failed
                  + ". Reason code gate_decline. Sort the standing issue or reroute to other claimees first.'")
        return 1

    print("\n  VERDICT: PASS — claimant is active, in good standing, past vesting; your balance clears the floor.")
    print(f"  Pay your share {args.amount}t directly to the claimant in <=100t parts "
          f"(reason REGISTRY-CLAIM), then DM zero-7: 'claim {args.claim_id}, share {args.amount}t paid to "
          f"member {member.get('member_no')} ({member.get('name')}), transfer id <id>'. The transfer id is the "
          "verification key — the operator matches your report against the claimant's statement "
          "(same id, same amount, counterparty = claimant, reason REGISTRY-CLAIM). A share paid but "
          "never reported leaves the claim short on verification until your report lands.")
    print("  Reply to the claimant: 'claimee_check passes against the live ledger; "
          f"sending my share for claim {args.claim_id} ({args.amount}t in parts if needed).'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
