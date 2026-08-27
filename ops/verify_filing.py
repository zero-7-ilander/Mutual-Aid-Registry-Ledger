#!/usr/bin/env python3
"""
verify_filing.py — operator-side claim filing verifier (Mutual Aid Registry).

The claimant runs ops/claim_check.py on their side: that proves their balance
on THEIR statement and writes the artifact. This tool re-verifies the filing
from the OPERATOR's seat, against the record, BEFORE a pending row lands in
claims.json (CLAIMS.md: "Record before notify", 00094-001 lesson 08-18 — the
row is the notice, the DM is only the pointer to it).

Input: the filing pack (claim_filing_pack.txt: header + [CLAIM id part i/N]
lines, as produced by claim_check.py 1.3.0) or the raw artifact JSON.
Reassembles the artifact and checks, per gate:

  1. PACK      header present, parts reassemble losslessly in order,
               header "artifact sha" == sha256(compact artifact)[:16],
               artifact parses and carries the claim block.
  2. LEDGER    artifact ledger_ref.sha256 == sha256(ledger, sort_keys)[:16]
               against the live GitHub contents API AND the local clone HEAD;
               at least one must match (the contents API can lag a fresh
               push by minutes — a match on either is a pass, noted).
  3. CLAIMANT  member exists, status active, entry complete
               (entry_verified == entry_total), vesting reached
               (first_claim_eligible <= today), dues current,
               claim amount within tier cap (1,500t; 2,000t premium).
  4. CLAIM ID  XXXXX-YYY form: member number matches the claimant,
               claim_no == prior claims by this member + 1.
  5. CLAIMEES  1..10 distinct members, each active + entry complete,
               none is the claimant, each share <= 250t (per-claimee gate),
               shares sum exactly to the claimed amount.
  6. COOLDOWN  no prior claim filed within 30 days whose status is paid
               (full or partial) or pending. void/rejected never opened
               the window and do not block re-file.

The claimant's balance itself is not re-checkable from the operator's seat
(the statement is theirs); the artifact records gate PASS + threshold, and
the balance_check block is echoed for the record.

Read-only: prints a per-gate verdict, touches nothing, writes nothing.
The operator commits the pending row only after every gate passes
(record before notify).

Exit codes
  0  every gate passes — the filing may be recorded
  1  a gate failed — do not record; send the printed reason
  2  technical error (pack unreadable, ledger unreachable, bad args)
"""

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

TOOL = "verify_filing.py"
VERSION = "1.0.0"
SHARE_MAX = 250            # per-claimee gate (claimee_check.py)
COOLDOWN_DAYS = 30         # September amendment (was 60)
CAP_STANDARD = 1500        # claim cap, starter/standard tiers
CAP_PREMIUM = 2000         # claim cap, premium tier
LEDGER_URL = "https://api.github.com/repos/zero-7-ilander/Mutual-Aid-Registry-Ledger/contents/ledger.json"
LOCAL_LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ledger.json")


def fetch_github_ledger():
    """Live ledger from the GitHub contents API. Returns (ledger, None) or (None, err)."""
    try:
        req = urllib.request.Request(LEDGER_URL, headers={"User-Agent": "registry-filing-verify"})
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.loads(r.read().decode())
        if payload.get("encoding") != "base64" or not payload.get("content"):
            raise ValueError("unexpected GitHub contents API payload")
        return json.loads(base64.b64decode(payload["content"]).decode()), None
    except Exception as e:
        return None, str(e)


def ledger_sha(ledger):
    """The hash claim_check.py stamps in the artifact (same serialization)."""
    return hashlib.sha256(json.dumps(ledger, sort_keys=True).encode()).hexdigest()[:16]


def load_local_ledger():
    try:
        with open(LOCAL_LEDGER) as f:
            return json.load(f)
    except Exception:
        return None


def today_utc():
    return datetime.now(timezone.utc).date()


def find_member(ledger, member_no):
    for m in ledger.get("members", []):
        if str(m.get("member_no")) == str(member_no):
            return m
    return None


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


def tier_cap(member):
    return CAP_PREMIUM if str(member.get("tier", "")).lower() == "premium" else CAP_STANDARD


def parse_pack(text):
    """Parse a claim_filing_pack.txt into (header_line, parts_dict, compact)."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines or not lines[0].startswith("CLAIM FILING "):
        return None, "no CLAIM FILING header line"
    header = lines[0]
    m = re.search(r"artifact sha ([0-9a-f]{16})", header)
    if not m:
        return None, "header carries no artifact sha"
    header_sha = m.group(1)
    parts = {}
    claim_id = None
    for ln in lines[1:]:
        pm = re.match(r"^\[CLAIM (\S+) part (\d+)/(\d+)\] (.*)$", ln)
        if not pm:
            return None, f"malformed part line: {ln[:60]!r}"
        cid, i, n, chunk = pm.group(1), int(pm.group(2)), int(pm.group(3)), pm.group(4)
        if claim_id is None:
            claim_id = cid
        if cid != claim_id:
            return None, f"part line carries a different claim id: {cid}"
        parts[i] = chunk
        if i < 1 or i > n:
            return None, f"part index {i} out of range 1..{n}"
        if len(ln) > 400:
            return None, f"part line {i} exceeds the 400-char DM cap ({len(ln)})"
    if not parts:
        return None, "no parts after the header"
    n = max(parts.keys())
    missing = [i for i in range(1, n + 1) if i not in parts]
    if missing:
        return None, f"missing part(s): {missing}"
    compact = "".join(parts[i] for i in range(1, n + 1))
    if hashlib.sha256(compact.encode()).hexdigest()[:16] != header_sha:
        return None, "header sha does not match the reassembled parts"
    try:
        artifact = json.loads(compact)
    except json.JSONDecodeError as e:
        return None, f"reassembled artifact does not parse: {e}"
    return {"header": header, "claim_id": claim_id, "n_parts": n,
            "compact": compact, "artifact": artifact}, None


def main():
    ap = argparse.ArgumentParser(description="Operator-side claim filing verifier")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pack", default=None, help="path to claim_filing_pack.txt")
    src.add_argument("--artifact", default=None, help="path to a raw claim_artifact.json")
    ap.add_argument("--today", default=None, help="date override YYYY-MM-DD (testing)")
    ap.add_argument("--version", action="version", version=f"{TOOL} {VERSION}")
    args = ap.parse_args()

    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else today_utc()

    print(f"[{TOOL} {VERSION}]  today {today}")

    # ---- 0. load the artifact ------------------------------------------------
    if args.pack:
        try:
            with open(args.pack) as f:
                pack_text = f.read()
        except OSError as e:
            sys.exit(f"FATAL: cannot read pack: {e}")
        parsed, err = parse_pack(pack_text)
        if err:
            print(f"  [FAIL] pack: {err}")
            return 1
        artifact = parsed["artifact"]
        print(f"  [PASS] pack: header ok, {parsed['n_parts']} part(s) reassembled, "
              f"sha matches ({parsed['claim_id']})")
    else:
        try:
            with open(args.artifact) as f:
                artifact = json.load(f)
        except OSError as e:
            sys.exit(f"FATAL: cannot read artifact: {e}")
        except json.JSONDecodeError as e:
            print(f"  [FAIL] artifact: does not parse: {e}")
            return 1
        print(f"  [PASS] artifact: parses ({args.artifact})")

    claim = artifact.get("claim") or {}
    claimees = artifact.get("claimees") or []
    bal = artifact.get("balance_check") or {}
    lref = artifact.get("ledger_ref") or {}
    amount = claim.get("amount")
    member_no = claim.get("member_no")
    claim_id = claim.get("claim_id")

    results = []  # (name, ok, detail)

    # ---- 1. LEDGER hash -------------------------------------------------------
    gh_ledger, gh_err = fetch_github_ledger()
    local_ledger = load_local_ledger()
    want = lref.get("sha256")
    matches = []
    if want:
        if gh_ledger is not None and ledger_sha(gh_ledger) == want:
            matches.append("github contents")
        if local_ledger is not None and ledger_sha(local_ledger) == want:
            matches.append("local HEAD")
    if not want:
        results.append(("ledger hash", False, "artifact carries no ledger_ref.sha256"))
    elif matches:
        results.append(("ledger hash", True,
                        f"artifact sha {want} matches {', '.join(matches)} "
                        f"(updated {lref.get('updated')})"))
    else:
        detail = "artifact sha matches neither the live contents API nor local HEAD"
        if gh_err:
            detail += f" (contents API unreachable: {gh_err[:80]})"
        results.append(("ledger hash", False, detail))

    ledger = local_ledger or gh_ledger
    if ledger is None:
        print("  [FAIL] ledger hash: no ledger source available; aborting the rest")
        return 2

    # ---- 2. CLAIMANT -----------------------------------------------------------
    if not member_no or amount is None or not claim_id:
        results.append(("claimant", False, "artifact claim block missing member_no/amount/claim_id"))
        member = None
    else:
        member = find_member(ledger, member_no)
        if not member:
            results.append(("claimant", False, f"member {member_no} not on the ledger"))
        else:
            checks = []
            if member.get("status") != "active":
                checks.append(f"status={member.get('status')} (must be active)")
            if member.get("entry_verified") != member.get("entry_total"):
                checks.append(f"entry {member.get('entry_verified')}/{member.get('entry_total')} not complete")
            elig = member.get("first_claim_eligible")
            if not elig:
                checks.append("no first_claim_eligible set")
            else:
                try:
                    if datetime.strptime(elig, "%Y-%m-%d").date() > today:
                        checks.append(f"vesting {elig} not reached")
                except Exception:
                    checks.append(f"unparseable first_claim_eligible {elig!r}")
            missed, ddetail = dues_missed(ledger, member)
            if missed >= 2:
                checks.append(ddetail)
            cap = tier_cap(member)
            if amount > cap:
                checks.append(f"amount {amount}t over tier cap {cap}t")
            if bal.get("passed") is not True:
                checks.append("artifact balance_check.passed is not true")
            if bal.get("threshold") != 1000:
                checks.append(f"artifact threshold {bal.get('threshold')} != charter 1,000")
            if checks:
                results.append(("claimant", False, f"member {member_no} {member.get('name')}: " + "; ".join(checks)))
            else:
                results.append(("claimant", True,
                                f"member {member_no} {member.get('name')}, {member.get('tier')}, active, "
                                f"entry {member.get('entry_verified')}/{member.get('entry_total')}, "
                                f"eligible {elig}; balance gate PASS ({bal.get('operating_balance')}t <= "
                                f"{bal.get('threshold')}t, claimant-side statement)"))

    # ---- 3. CLAIM ID -----------------------------------------------------------
    if member is not None:
        m = re.match(r"^(\d{5})-(\d{3})$", str(claim_id))
        prior = [c for c in ledger.get("claims", [])
                 if str(c.get("member_no")) == str(member_no)]
        if not m:
            results.append(("claim id", False, f"{claim_id!r} is not XXXXX-YYY form"))
        elif m.group(1) != f"{int(member_no):05d}":
            results.append(("claim id", False,
                            f"id member {m.group(1)} != claimant {int(member_no):05d}"))
        elif int(m.group(2)) != len(prior) + 1:
            results.append(("claim id", False,
                            f"id claim_no {int(m.group(2))} != prior claims {len(prior)} + 1"))
        else:
            results.append(("claim id", True, f"{claim_id} (member {m.group(1)}, claim {m.group(2)}; "
                                              f"{len(prior)} prior claim(s) on file)"))

    # ---- 4. CLAIMEES -------------------------------------------------------------
    if member is not None:
        if not claimees:
            results.append(("claimees", False, "artifact lists no claimees"))
        elif len(claimees) > 10:
            results.append(("claimees", False, f"{len(claimees)} claimees (max 10)"))
        else:
            problems = []
            seen = set()
            total = 0
            for c in claimees:
                cm = find_member(ledger, c.get("member_no"))
                cid_ = str(c.get("member_no"))
                if cid_ in seen:
                    problems.append(f"duplicate claimee {cid_}")
                seen.add(cid_)
                if str(c.get("member_no")) == str(member_no):
                    problems.append(f"claimee {cid_} is the claimant")
                if not cm:
                    problems.append(f"claimee {cid_} not on the ledger")
                    continue
                if cm.get("status") != "active":
                    problems.append(f"claimee {cid_} status={cm.get('status')}")
                if cm.get("entry_verified") != cm.get("entry_total"):
                    problems.append(f"claimee {cid_} entry not complete")
                share = c.get("suggested_amount")
                if share is None:
                    problems.append(f"claimee {cid_} has no suggested_amount")
                elif share > SHARE_MAX:
                    problems.append(f"claimee {cid_} share {share}t over {SHARE_MAX}t")
                else:
                    total += share
            if amount is not None and total != amount:
                problems.append(f"shares sum {total}t != claimed {amount}t")
            if problems:
                results.append(("claimees", False, "; ".join(problems[:8]) +
                                ("; …" if len(problems) > 8 else "")))
            else:
                results.append(("claimees", True,
                                f"{len(claimees)} distinct active members, entry complete, "
                                f"shares sum {total}t == {amount}t, each <= {SHARE_MAX}t"))

    # ---- 5. COOLDOWN ---------------------------------------------------------------
    if member is not None:
        filed = claim.get("date_filed") or (args.today or today.isoformat())
        try:
            filed_d = datetime.fromisoformat(str(filed).replace("Z", "+00:00")).date()
        except Exception:
            filed_d = today
        hits = []
        for c in ledger.get("claims", []):
            if str(c.get("member_no")) != str(member_no):
                continue
            try:
                cd = datetime.fromisoformat(str(c.get("date_filed")).replace("Z", "+00:00")).date()
            except Exception:
                continue
            if (filed_d - cd).days < COOLDOWN_DAYS and c.get("status") in ("paid", "pending"):
                hits.append(f"{c.get('claim_id')} {c.get('status')} filed {cd}")
        if hits:
            results.append(("cooldown", False,
                            f"{COOLDOWN_DAYS}d window open: " + "; ".join(hits)))
        else:
            results.append(("cooldown", True,
                            f"no paid/pending prior claim within {COOLDOWN_DAYS}d of filing"))

    # ---- verdict ---------------------------------------------------------------------
    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    if failed:
        print("\n  VERDICT: DO NOT RECORD — filing does not pass the operator gate.")
        print("  Send the claimant the failing gates; a corrected filing re-runs this tool.")
        return 1
    print("\n  VERDICT: PASS — record the pending row first (record before notify),")
    print("  then ask the claimees. The row is the notice; the DM is only the pointer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
