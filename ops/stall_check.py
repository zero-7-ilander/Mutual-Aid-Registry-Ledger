#!/usr/bin/env python3
"""stall_check.py — hour-scale stall radar for the Mutual Aid Registry ledger.

Read-only. Watches the claims + ask queue for the gap that left 00094-001
at 8/10 for 11h on 08-18: a pending claim aging without movement because
the ask never landed or a claimee went silent.

Sits UNDER the daily 07:30 sweep's day-scale aging (7d void, 7d nudge).
The sweep handles the law; this radar handles the hours.

Run discipline (radar): PULL FIRST, read live, then flag.
    python3 ops/stall_check.py --repo PATH --pull [--stall-hours N]
--pull refreshes the clone (git pull --ff-only) and REFUSES to run on a
dirty tree. Every run prints the HEAD sha it read, so a stale receipt
shows itself. Plain runs (no --pull) stay fully read-only but still print
the sha.

Exit: 0 clean / 1 stalls found / 2 error. Stdlib only. Touches nothing
without --pull.
"""
# Contribution: Bon 220 (agent 346493658561777664), 2026-08-25.
# Fix 2026-08-27 (Bon 220 patch, reviewed + landed): type-3 finding — a pending
# claim with NO ask-queue row flags at stall-hours (the 00005-001 pattern: queue
# never rotated on filing). parse_ts naive-datetime crash fixed earlier (122d535).
# Guard 2026-08-28 (Bon 220 patch, reviewed + landed): pull-first run discipline.
# Root cause on record: 08-27 the radar fired a type-1 STALL on schedule but
# against a STALE clone (last sync 12:30Z; live HEAD had closed the claim 10/10
# at 17:30Z). The flag clock worked; the clone was the liar. Same class as the
# pinned-sha rule on the Keeper's seat. Guard = --pull (ff-only, dirty-tree
# refusal) + HEAD sha on every run receipt.
# Reviewed by Zero 2026-08-25 before landing: read-only (all opens "r"),
# stdlib only, exit 0/1/2 verified (live repo clean; synthetic stuck claim
# 3 flags exit 1). Schema fields checked against claims.json +
# ops/claims_ask_queue.json. File lands as sent, plus this header.

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

STALL_DEFAULT_HOURS = 8


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value: str) -> datetime | None:
    """Parse ISO-8601 or date-only stamps; return aware datetime or None."""
    if not value:
        return None
    s = str(value).strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        # fromisoformat accepts date-only strings and returns a NAIVE datetime;
        # normalize so max() over mixed candidates cannot TypeError.
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:  # date only, e.g. 2026-08-18
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_queue(ops_dir: Path):
    """claims_ask_queue.json is a bare claim object today; tolerate list/wrapper."""
    p = ops_dir / "claims_ask_queue.json"
    if not p.exists():
        return []
    data = load_json(p)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "claim_id" in data:
            return [data]
        for key in ("claims", "queue"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def repo_head_sha(repo: Path) -> str:
    """Read the HEAD sha without git (stdlib only). 'unknown' if unreadable."""
    try:
        git_dir = repo / ".git"
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split("ref:", 1)[1].strip()
            sha = (git_dir / ref).read_text(encoding="utf-8").strip()
        else:  # detached HEAD
            sha = head
        return sha if len(sha) == 40 else "unknown"
    except Exception:  # noqa: BLE001 — cosmetic; the run still proceeds
        return "unknown"


def pull_first(repo: Path) -> tuple[bool, str]:
    """Pull-first guard: refuse dirty trees, then git pull --ff-only.

    A dirty clone is a liar (local edits silently shadow the live ledger);
    a failed pull means the run would read stale data, so fail loud.
    """
    try:
        status = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as e:  # noqa: BLE001
        return False, f"git unavailable: {e}"
    if status.returncode != 0:
        return False, f"git status failed: {(status.stderr or status.stdout).strip()}"
    if status.stdout.strip():
        return False, f"dirty tree ({status.stdout.count(chr(10)) + 1} change(s)); pull refused"
    try:
        pull = subprocess.run(
            ["git", "-C", str(repo), "pull", "--ff-only"],
            capture_output=True, text=True, timeout=120,
        )
    except Exception as e:  # noqa: BLE001
        return False, f"git pull failed: {e}"
    if pull.returncode != 0:
        return False, (pull.stderr or pull.stdout).strip()
    return True, (pull.stdout or pull.stderr).strip()


def claim_last_movement(claim: dict) -> datetime | None:
    """Newest timestamp of any recorded movement on a claim."""
    candidates = [parse_ts(claim.get("date_filed"))]
    for share in claim.get("paid_by", []) or []:
        candidates.append(parse_ts(share.get("reported_at") or share.get("date")))
    for u in claim.get("unpaid", []) or []:
        candidates.append(parse_ts(u.get("date") or u.get("reported_at")))
    candidates.append(parse_ts(claim.get("nudged")))
    candidates.append(parse_ts(claim.get("closed_at")))
    valid = [c for c in candidates if c]
    return max(valid) if valid else None


def expected_shares(claim: dict, q: dict) -> int:
    """Expected claimee count from the queue's own share (e.g. 2000/200 = 10)."""
    amount = claim.get("amount_filed") or 0
    share = q.get("share") or 0
    if amount > 0 and share > 0:
        return max(1, round(amount / share))
    return 10  # fallback: picker caps at 10 claimees


def check_repo(repo: Path, stall_hours: int) -> list:
    findings = []
    ops_dir = repo / "ops"
    claims_data = load_json(repo / "claims.json")
    claims = claims_data.get("claims", []) if isinstance(claims_data, dict) else claims_data
    queue = load_queue(ops_dir)
    queue_by_claim = {q.get("claim_id"): q for q in queue if q.get("claim_id")}

    now = now_utc()
    for claim in claims:
        if claim.get("status") != "pending":
            continue
        claim_id = claim.get("claim_id", "?")
        last = claim_last_movement(claim)
        filed = parse_ts(claim.get("date_filed"))
        paid_n = len(claim.get("paid_by", []) or [])
        unpaid_n = len(claim.get("unpaid", []) or [])

        # Finding type 1: claim aging without any movement.
        if last is not None and filed is not None:
            hours_idle = (now - last).total_seconds() / 3600
            hours_live = (now - filed).total_seconds() / 3600
            if hours_idle >= stall_hours and hours_live >= stall_hours:
                findings.append(
                    f"STALL claim={claim_id} status=pending paid={paid_n} "
                    f"unpaid={unpaid_n} idle={hours_idle:.1f}h "
                    f"(filed {hours_live:.1f}h ago, last movement {last.isoformat()})"
                )

        # Finding type 2: ask queue incomplete for a pending claim.
        q = queue_by_claim.get(claim_id)
        if q is not None:
            delivered_n = len(q.get("delivered", []) or [])
            pending_n = len(q.get("pending", []) or [])
            want = expected_shares(claim, q)
            queued = parse_ts(q.get("queued_utc"))
            queue_age_h = (now - queued).total_seconds() / 3600 if queued else None
            if delivered_n < want and queue_age_h is not None and queue_age_h >= stall_hours:
                findings.append(
                    f"STALL queue={claim_id} delivered={delivered_n}/{want} "
                    f"pending={pending_n} queue_age={queue_age_h:.1f}h "
                    f"(queued {q.get('queued_utc')})"
                )
            if pending_n and queue_age_h is not None and queue_age_h >= stall_hours:
                findings.append(
                    f"STALL queue={claim_id} ask stuck: {pending_n} pending "
                    f"for {queue_age_h:.1f}h (intro cap / no thread pattern)"
                )

        # Finding type 3: pending claim with NO ask-queue row (00005-001
        # pattern: queue never rotated on filing). Invisible to type 2; flags
        # so the operator confirms the ask state instead of assuming a
        # missed notification.
        if q is None and last is not None:
            hours_idle = (now - last).total_seconds() / 3600
            if hours_idle >= stall_hours:
                findings.append(
                    f"STALL queue={claim_id} NO ROW in claims_ask_queue "
                    f"idle={hours_idle:.1f}h (queue not rotated on filing?)"
                )
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="MAR stall radar (read-only without --pull)")
    ap.add_argument("--repo", type=Path, default=Path("."),
                    help="path to registry repo (default: cwd)")
    ap.add_argument("--stall-hours", type=float, default=STALL_DEFAULT_HOURS,
                    help=f"hours without movement that counts as a stall (default {STALL_DEFAULT_HOURS})")
    ap.add_argument("--pull", action="store_true",
                    help="pull-first: git pull --ff-only before reading; refuses dirty trees")
    args = ap.parse_args()

    repo = args.repo.resolve()
    sha = repo_head_sha(repo)
    if args.pull:
        ok, msg = pull_first(repo)
        if not ok:
            print(f"error: pull-first refused: {msg}", file=sys.stderr)
            return 2
        sha = repo_head_sha(repo)  # re-read: the pull may have moved HEAD
    print(f"radar at {sha} ({repo})")

    if not (repo / "claims.json").exists():
        print(f"error: no claims.json in {repo}", file=sys.stderr)
        return 2
    try:
        findings = check_repo(repo, args.stall_hours)
    except Exception as e:  # noqa: BLE001 — read-only tool, fail loud
        print(f"error: {e}", file=sys.stderr)
        return 2

    if findings:
        for line in findings:
            print(line)
        print(f"{len(findings)} stall(s) in {repo}")
        return 1
    print("clean: no stalls (claims all closed/paid, queue complete)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
