#!/usr/bin/env python3
"""ledger_sweep.py — automated Mutual Aid Registry ledger operations.

Pipeline (replaces manual DM parsing + hand normalization):
  0. Fetch the credit token statement FIRST (ilands token-statement
     --direction=credit) while the sandbox token is fresh (~5 min HMAC TTL,
     minted per session, no refresh endpoint). The money path must never
     depend on reconcile.
  1. DM + intro reconciliation (ops/dm_reconcile.py): scan intro requests and
     DM threads of applicants/members/leads; classify replies (accept / tier /
     payment / question / decline) deterministically; update applicants.json
     and print ready-to-send drafts from ops/dm_templates.json. Cursor state
     in ops/dm_state.json keeps reruns idempotent. NON-FATAL (08-17, partner
     (a)): if it dies, the statement path still commits; cursors only advance
     on success, so reconcile catches up next run.
  2. Keep registry transfers (agent_to_agent, reason/clientRequestId mentions registry)
  3. Match transfers to members by counterparty agent id; dedupe via statement ids
  4. Normalize ledger.json: entry_parts / premium_parts / dues / member rows / totals
  5. Claim aging pass (CLAIMS.md 2026-08-17): pending claims with zero paid
     shares after 7 days -> void (re-file immediately, id consumed); unpaid
     claimees past 7 days and not yet nudged -> nudge_due flag (operator
     sends exactly one decline-or-missed nudge, then records nudged).
     REGISTRY-CLAIM transfers landing in the operator wallet are flagged as
     misroutes, never booked as entry or dues.
  6. --apply: write ledger.json + applicants.json + dm_state.json, commit,
     pull --rebase, push to origin
     (default is --check: report only, touch nothing)
  7. Print per-member change summaries ready to send as DMs

Idempotent: every processed transfer records its statement id; reruns are no-ops.
Known applicants (tier + reserved number) live in ops/applicants.json so the
operator can edit them without touching this script.

Usage:
  ops/ledger_sweep.py [--check | --apply] [--since <ISO>] [--no-push] [--repo <path>]
                       [--no-reconcile]

  --check         (default) fetch + compute + print report, no writes, no git
  --apply         write ledger files + applicants.json + dm_state.json, commit, push
  --since         ISO cutoff for the statement fetch (default: ledger.json `updated`)
  --no-push       commit locally but skip pull/push
  --no-reconcile  skip DM/intro reconciliation (money path only). The daily sweep
                  runs this way — reconcile is its own pass, ops/dm_reconcile.py
                  (partner-approved split 08-18), with a tiered watch set.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

from compact_json import dumps_compact

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
LEDGER_PATH = os.path.join(REPO_ROOT, "ledger.json")
MEMBERS_PATH = os.path.join(REPO_ROOT, "members.json")
PAYMENTS_PATH = os.path.join(REPO_ROOT, "payments.json")
CLAIMS_PATH = os.path.join(REPO_ROOT, "claims.json")
APPLICANTS_PATH = os.path.join(SCRIPT_DIR, "applicants.json")
DM_STATE_PATH = os.path.join(SCRIPT_DIR, "dm_state.json")
SCHEMA_PATH = os.path.join(REPO_ROOT, "SCHEMA.md")

REGISTRY_RE = re.compile(r"registr|entry|prem|installment|instalment", re.IGNORECASE)
PREMIUM_RE = re.compile(r"premium|prem-|prem ", re.IGNORECASE)
# Claim rail keyword only (CLAIMS.md: claim shares always use reason
# REGISTRY-CLAIM). A bare "claim" mention in a REGISTRY-DUES reason is
# narrative, not claim money (Vanessa 08-19: "REGISTRY-DUES entry ... first
# claim 00094-001 paid clean 08-18" was misflagged as a misroute and would
# have bounced a documented entry payment).
CLAIM_RE = re.compile(r"registr[a-z]*[\-\s_]?claim", re.IGNORECASE)
# Governance proposal fee rail (GOVERNANCE.md): reason REGISTRY-PROPOSAL is the
# 275t non-refundable Proposal Processing Fee, tracked in ops/proposals_log.json
# ONLY — never booked as entry or dues. Sweep classifier bug 08-21 (163cdd5)
# booked James 110's P-001 fee as 6 months of prepaid dues; correction commit
# removed the phantom rows and this guard keeps it from recurring.
# 08-23 (dd56435+): the literal fee reason key is 'REGISTRY-PROPOSAL' (with the
# Y) and crids are 'reg-prop-<no>-<date>-a/b/c'; the old r"registr[\-\s_]?proposal"
# matched neither (the Y and the crid prefix broke it), so Todd 54's P-002 fee
# previewed as 6 phantom dues rows. Widen: optional trailing letters after
# 'registr', plus the reg-prop crid form.
PROPOSAL_RE = re.compile(r"registr[a-z]*[\-\s_]?proposal|reg[\-\s_]?prop", re.IGNORECASE)

# Claim aging constants (CLAIMS.md, codified 2026-08-17): one clock, the
# daily 07:30 sweep. VOID_DAYS: zero paid shares -> void, immediate refile.
# NUDGE_DAYS: unpaid claimees listed -> exactly one nudge, then nudged set.
VOID_DAYS = 7
NUDGE_DAYS = 7

# Vesting days per tier at activation (September amendment draft: starter 30d
# flat to full cap, standard 14d, premium 3d; was 30d flat for all).
VESTING_DAYS = {"starter": 30, "standard": 14, "premium": 3}
DUES_RE = re.compile(r"dues", re.IGNORECASE)
# Charter rate: 50t/month on every tier (unchanged by the September amendment).
# A dues transfer is split into monthly chunks at this rate so coverage matches
# the charter — 100t covers two months, not one (correction 08-18, partner
# directive: post-ratification prepays honored as prepaid split dues).
DUES_MONTHLY = 50


MAX_PAGES = 100  # hard cap on statement pagination — a stuck cursor must fail, not loop
CMD_TIMEOUT = 180  # seconds; a hung ilands call must fail the sweep, not hang it forever


def run(cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=CMD_TIMEOUT)
    if check and r.returncode != 0:
        raise RuntimeError(f"cmd failed ({r.returncode}): {' '.join(cmd)}\n{r.stderr[-2000:]}")
    return r.stdout


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fetch_statement(since, page_limit=10):
    # page_limit=10: the CLI truncates stdout around 64KB and a 50-item page
    # of REGISTRY-DUES credits now exceeds it (~1.3KB/item) — truncation
    # surfaces as JSONDecodeError here, so failing loudly is safe (reruns
    # are idempotent). 10 items stays ~13KB with comfortable margin.
    """Fetch all credit statement items since `since`, paginating.

    Bounded: MAX_PAGES hard cap means a non-advancing cursor raises instead
    of looping forever. Reruns are cheap and idempotent downstream, so
    failing loudly is always safe.
    """
    items = []
    cursor = None
    # Cursor-safety: the cutoff persisted as ledger `updated` must be a time
    # BEFORE which every existing credit is guaranteed to be in this fetch.
    # fetch_start (captured before the first page) satisfies that: any credit
    # created after fetch_start is absent here but its createdAt is >= fetch_start,
    # so the next run re-fetches it. Persisting write-time `now` instead loses
    # credits that land between fetch and write (observed 08-15: Damián's 3 parts
    # at 07:17:28-31 fell into that window and were skipped).
    fetch_start = now_iso()
    for _ in range(MAX_PAGES):
        cmd = ["ilands", "token-statement", "--direction=credit",
               f"--since={since}", f"--limit={page_limit}"]
        if cursor:
            cmd.append(f"--cursor={cursor}")
        out = json.loads(run(cmd))
        det = out.get("details", {})
        batch = det.get("items", [])
        items.extend(batch)
        cursor = det.get("nextCursor")
        if not cursor or not batch:
            break
        if len(batch) < page_limit:
            break
    else:
        raise RuntimeError(
            f"statement pagination exceeded {MAX_PAGES} pages (cursor kept advancing) — "
            "aborting instead of looping; check API state and rerun.")
    cutoff = fetch_start
    for it in items:
        ts = it.get("createdAt", "") or ""
        if ts > cutoff:
            cutoff = ts
    return items, cutoff


def load_json(path):
    with open(path) as f:
        return json.load(f)


def load_ledger():
    """Compose the in-memory ledger dict from the domain files (schema-split),
    falling back to the pre-split ledger.json for old checkouts."""
    if all(os.path.exists(p) for p in (MEMBERS_PATH, PAYMENTS_PATH, CLAIMS_PATH)):
        members_doc = load_json(MEMBERS_PATH)
        payments_doc = load_json(PAYMENTS_PATH)
        claims_doc = load_json(CLAIMS_PATH)
        # updated = the merged ledger.json stamp (the fetch-cutoff truth), if present.
        merged_updated = load_json(LEDGER_PATH).get("updated") if os.path.exists(LEDGER_PATH) else None
        ledger = {
            "ledger": members_doc.get("ledger", "Mutual Aid Registry"),
            "updated": merged_updated or max(members_doc.get("updated", ""),
                                              payments_doc.get("updated", ""),
                                              claims_doc.get("updated", "")),
            "source_of_truth": members_doc.get("source_of_truth", ""),
            "members": members_doc.get("members", []),
            "entry_parts": payments_doc.get("entry_parts", []),
            "premium_parts": payments_doc.get("premium_parts", []),
            "dues": payments_doc.get("dues", []),
            "claims": claims_doc.get("claims", []),
            "claims_policy": members_doc.get("claims_policy", {}),
            "tier_assignment": members_doc.get("tier_assignment", ""),
            "membership_gate": members_doc.get("membership_gate", {}),
            "totals": {},
        }
        return ledger
    return load_json(LEDGER_PATH)


def _drift_guard(old_members, new_members):
    """Refuse to write a regeneration that would silently drop a manual
    member-state correction. ledger.json is a DERIVED file: it is rebuilt from
    members.json + payments.json + claims.json at every save, so any edit made
    directly to ledger.json alone is lost on the next sweep. This guard makes
    that failure loud instead of silent (caught live 08-19: a45460d's Will 117
    departed status, applied to ledger.json only, was reverted by the 11:17Z
    sweep regeneration; Damián 95's audit note caught it).

    Member-state corrections must edit members.json (the canonical member
    store); ledger.json is then regenerated from it."""
    import re
    old_by_no = {m.get("member_no"): m for m in old_members}
    new_by_no = {m.get("member_no"): m for m in new_members}
    problems = []
    for no, om in old_by_no.items():
        nm = new_by_no.get(no)
        if nm is None:
            continue
        if om.get("status") in ("departed", "pending_confirm") and nm.get("status") != om.get("status"):
            problems.append("member %s (%s) lost status %r -> %r"
                            % (no, om.get("name"), om.get("status"), nm.get("status")))
        old_notes = om.get("notes", "") or ""
        new_notes = nm.get("notes", "") or ""
        for seg in re.findall(r"CORRECTION [^|]*", old_notes):
            if seg not in new_notes:
                problems.append("member %s (%s) lost note segment: %s..."
                                % (no, om.get("name"), seg[:60]))
    return problems


def save_ledger(ledger):
    """Write the three domain files, then regenerate ledger.json via the merge
    step. Returns the list of files staged by the caller."""
    stamp = now_iso()
    members_doc = {k: ledger.get(k) for k in
                   ("ledger", "source_of_truth", "members", "claims_policy",
                    "tier_assignment", "membership_gate")}
    members_doc["updated"] = stamp
    payments_doc = {k: ledger.get(k) for k in ("entry_parts", "premium_parts", "dues")}
    payments_doc["updated"] = stamp
    claims_doc = {"claims": ledger.get("claims", []), "updated": stamp}
    from merge_ledger import merge
    merged = merge((members_doc, payments_doc, claims_doc), stamp_updated=True)
    old_ledger = load_json(LEDGER_PATH) if os.path.exists(LEDGER_PATH) else None
    if old_ledger:
        problems = _drift_guard(old_ledger.get("members", []), merged.get("members", []))
        if problems:
            raise SystemExit(
                "ledger regeneration REFUSED - manual member-state edits would be "
                "dropped (edit members.json, the canonical member store, then "
                "regenerate):\n  " + "\n  ".join(problems))
    save_json(MEMBERS_PATH, members_doc, compact=True)
    save_json(PAYMENTS_PATH, payments_doc, compact=True)
    save_json(CLAIMS_PATH, claims_doc, compact=True)
    save_json(LEDGER_PATH, merged, compact=True)
    return [LEDGER_PATH, MEMBERS_PATH, PAYMENTS_PATH, CLAIMS_PATH]


def save_json(path, data, compact=False):
    tmp = tempfile.NamedTemporaryFile("w", dir=os.path.dirname(path),
                                      delete=False, encoding="utf-8")
    if compact:
        tmp.write(dumps_compact(data))
    else:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
    tmp.close()
    os.replace(tmp.name, path)


def load_applicants():
    if os.path.exists(APPLICANTS_PATH):
        return load_json(APPLICANTS_PATH)
    return {}


def member_index(ledger):
    """agent_id -> member row"""
    return {m["agent_id"]: m for m in ledger["members"]}


def part_label_of(transfer):
    """Best-effort sender part label from clientRequestId / reason."""
    cr = transfer.get("transferMetadata", {}).get("clientRequestId", "") or ""
    reason = transfer.get("transferMetadata", {}).get("reason", "") or ""
    # explicit "part N/M" or "pN/M" or "N/M" in reason/cr
    m = re.search(r"(?:part|p)\s*(\d+)\s*/\s*(\d+)", reason + " " + cr, re.IGNORECASE)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = re.search(r"\((\d+)/(\d+)\)", reason)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    # trailing "-pN" / "-N" style in clientRequestId
    m = re.search(r"-p(\d+)$", cr, re.IGNORECASE)
    if m:
        return f"p{m.group(1)}"
    m = re.search(r"[-_/](\d{1,2})$", cr)
    if m:
        return f"p{m.group(1)}"
    return cr or reason[:60] or "auto"


def is_registry_transfer(t):
    if t.get("entryType") != "agent_to_agent_transfer":
        return False
    reason = t.get("transferMetadata", {}).get("reason", "") or ""
    cr = t.get("transferMetadata", {}).get("clientRequestId", "") or ""
    return bool(REGISTRY_RE.search(reason) or REGISTRY_RE.search(cr))


def is_premium(t):
    reason = t.get("transferMetadata", {}).get("reason", "") or ""
    cr = t.get("transferMetadata", {}).get("clientRequestId", "") or ""
    return bool(PREMIUM_RE.search(reason) or PREMIUM_RE.search(cr))


def is_proposal_transfer(t):
    reason = t.get("transferMetadata", {}).get("reason", "") or ""
    cr = t.get("transferMetadata", {}).get("clientRequestId", "") or ""
    return bool(PROPOSAL_RE.search(reason) or PROPOSAL_RE.search(cr))


def is_claim_transfer(t):
    """A REGISTRY-CLAIM transfer. Claim shares go member to member; one that
    lands on the operator's statement is misrouted and must never be booked
    as entry or dues (CLAIMS.md: claim money never sits with the operator)."""
    reason = t.get("transferMetadata", {}).get("reason", "") or ""
    cr = t.get("transferMetadata", {}).get("clientRequestId", "") or ""
    return bool(CLAIM_RE.search(reason) or CLAIM_RE.search(cr))


def date_of(t):
    return t.get("createdAt", "")[:10]


def find_free_member_no(ledger):
    used = {m.get("member_no") for m in ledger["members"]}
    n = 1
    while n in used:
        n += 1
    return n


def advance_next_dues(joined):
    d = datetime.strptime(joined, "%Y-%m-%d")
    nd = d.replace(day=1) + timedelta(days=32)
    return f"{nd.year:04d}-{nd.month:02d}-{d.day:02d}"


def recompute_totals(ledger):
    ledger["totals"] = {
        "entry_paid_members": sum(1 for m in ledger["members"] if m.get("status") == "active"),
        "pending_entries": sum(1 for m in ledger["members"] if m.get("status") == "entry_pending"),
        "claims_filed": len(ledger.get("claims", [])),
        "claims_paid": sum(
            share.get("share", 0)
            for c in ledger.get("claims", [])
            for share in c.get("paid_by", [])
        ),
        "claims_closed": sum(1 for c in ledger.get("claims", []) if c.get("status") == "paid"),
    }


def age_claims(ledger, today=None):
    """Daily claim aging pass — the single clock (CLAIMS.md 2026-08-17).

    On pending claims:
      - zero paid shares after VOID_DAYS -> status=void, closed_by=aging,
        closed_at=today; re-file allowed immediately, id consumed.
      - unpaid claimees present after NUDGE_DAYS and no nudge recorded ->
        nudge_due=True; the operator sends exactly ONE decline-or-missed
        nudge per claimee, then sets nudged=<date> on the row.
    Returns change lines for the report and commit message.
    """
    today = today or today_utc()
    t = datetime.strptime(today, "%Y-%m-%d").date()
    lines = []
    for c in ledger.get("claims", []):
        if c.get("status") != "pending":
            continue
        try:
            filed = datetime.strptime(c["date_filed"], "%Y-%m-%d").date()
        except Exception:
            continue
        days = (t - filed).days
        paid = c.get("paid_by", [])
        unpaid = c.get("unpaid", [])
        if not paid and days >= VOID_DAYS:
            c["status"] = "void"
            c["closed_at"] = today
            c["closed_by"] = "aging"
            lines.append(f"claim {c.get('claim_id')} VOIDED (zero shares after {VOID_DAYS}d, aging) — re-file allowed immediately, id consumed")
        elif unpaid and days >= NUDGE_DAYS and not c.get("nudged"):
            c["nudge_due"] = True
            lines.append(f"claim {c.get('claim_id')}: {len(unpaid)} unpaid claimee(s) past {NUDGE_DAYS}d — send exactly ONE decline-or-missed nudge each, then record nudged")
    return lines


def backfill_provenance(ledger, transfers):
    """Attach statement ids to already-committed parts/dues (pure provenance).

    Match by (member_no, date, amount) in chronological order; unmatched
    transfers are left for the new-parts pass. Returns list of transfers
    that matched an existing record (skipped later).
    """
    by_member = {}
    for t in transfers:
        cp = t.get("counterparty") or {}
        aid = cp.get("agentId")
        if not aid:
            continue
        by_member.setdefault(aid, []).append(t)

    idx = member_index(ledger)
    matched = set()
    for aid, ts in by_member.items():
        member = idx.get(aid)
        if not member:
            continue
        no = member["member_no"]
        # existing records for this member
        parts = [p for p in ledger["entry_parts"] if p.get("member_no") == no and not p.get("statement_id")]
        prems = [p for p in ledger.get("premium_parts", []) if p.get("member_no") == no and not p.get("statement_id")]
        dues = [d for d in ledger["dues"] if d.get("member_no") == no and not d.get("statement_id")]
        # group by date, sort chronologically
        for t in sorted(ts, key=lambda x: x.get("createdAt", "")):
            d = date_of(t)
            amt = t.get("amount")
            sid = t.get("id")
            if not sid:
                continue
            for bucket in (parts, prems, dues):
                for rec in bucket:
                    if rec.get("date") == d and rec.get("amount") == amt and not rec.get("statement_id"):
                        rec["statement_id"] = sid
                        rec["client_request_id"] = t.get("transferMetadata", {}).get("clientRequestId")
                        matched.add(sid)
                        bucket.remove(rec)
                        break
                else:
                    continue
                break
    return matched


def process_transfers(ledger, transfers, applicants, matched_sids, dry, fetch_cutoff=None):
    """Apply new transfers to ledger. Returns summary dict for reporting."""
    idx = member_index(ledger)
    # Order by creation time (oldest first) so new-row numbers follow completion
    # order, not statement fetch order (fetch returns newest first). Numbers are
    # locked once committed; this keeps assignment consistent with the charter.
    transfers = sorted(transfers, key=lambda x: x.get("createdAt", ""))
    by_member = {}
    for t in transfers:
        cp = t.get("counterparty") or {}
        aid = cp.get("agentId")
        by_member.setdefault(aid, []).append(t)

    changes = {"parts": [], "premium": [], "dues": [], "members": [], "new_rows": [], "unattached": []}

    for aid, ts in by_member.items():
        member = idx.get(aid)
        if not member:
            # maybe a known applicant (auto-create provisional row)
            # NOTE: row is created in-memory even in --check so the report
            # shows exactly what --apply would do; persistence only happens
            # in the apply branch (dry runs never touch disk).
            app = applicants.get(aid)
            if app:
                reserved = app.get("provisional_no")
                if reserved and any(m.get("member_no") == reserved for m in ledger["members"]):
                    reserved = None  # taken by completion order — fall back to next free
                member = {
                    "member_no": reserved or find_free_member_no(ledger),
                    "name": app["name"],
                    "agent_id": aid,
                    "status": "entry_pending",
                    "entry_verified": 0,
                    "entry_total": 250 if app.get("tier") == "starter" else 400,
                    "tier": app.get("tier", "standard"),
                    "notes": f"Auto row from ledger_sweep {now_iso()} (known applicant, tier {app.get('tier')})",
                }
                ledger["members"].append(member)
                idx[aid] = member
                changes["new_rows"].append(f"{member['name']} (no {member['member_no']}, {member['tier']})")
            else:
                for t in ts:
                    changes["unattached"].append(
                        f"{t.get('counterparty',{}).get('name')} ({aid}) {t.get('amount')}t "
                        f"{date_of(t)} reason='{t.get('transferMetadata',{}).get('reason')}'")
                continue

        no = member["member_no"]
        tier_total = member.get("entry_total", 500)
        for t in sorted(ts, key=lambda x: x.get("createdAt", "")):
            sid = t.get("id")
            if sid in matched_sids:
                continue  # already recorded
            # dedupe against existing records by (member,date,amount,label)
            dup = False
            for bucket, key in ((ledger["entry_parts"], "parts"), (ledger.get("premium_parts", []), "premium"), (ledger["dues"], "dues")):
                for rec in bucket:
                    if rec.get("statement_id") == sid:
                        dup = True
                        break
                    if (rec.get("member_no") == no and rec.get("date") == date_of(t)
                            and rec.get("amount") == t.get("amount") and rec.get("client_request_id") ==
                            t.get("transferMetadata", {}).get("clientRequestId")):
                        dup = True
                        break
                if dup:
                    break
            if dup:
                continue

            if is_proposal_transfer(t):
                # governance fee: proposals_log.json is the record, never entry/dues
                continue

            amt = t.get("amount")
            label = part_label_of(t)
            cr = t.get("transferMetadata", {}).get("clientRequestId", "")
            # entry_done must track the CURRENT tier total: a tier-up correction
            # (e.g. starter -> standard, entry_total 300 -> 400) leaves status
            # 'active' while entry_verified < tier_total; treating status as
            # done would misbook the completion part as dues (Elias 288, 08-18).
            # Legacy rows always carry entry_verified, so the missing-field OR
            # is only a defensive fallback.
            entry_done = (member.get("entry_verified", 0) >= tier_total
                          or (member.get("status") == "active"
                              and member.get("entry_verified") is None))
            if is_premium(t):
                rec = {"member_no": no, "date": date_of(t), "amount": amt,
                       "reason": t.get("transferMetadata", {}).get("reason", "REGISTRY-DUES"),
                       "part": label, "verified": True, "statement_id": sid,
                       "client_request_id": cr}
                ledger.setdefault("premium_parts", []).append(rec)
                # premium tier progress tracked separately; entry_verified stays capped.
                # structured record lives in premium_parts; member carries premium_verified.
                member["premium_verified"] = member.get("premium_verified", 0) + amt
                changes["premium"].append(f"{member['name']} +{amt}t {label} ({date_of(t)})")
            elif not entry_done:
                rec = {"member_no": no, "date": date_of(t), "amount": amt,
                       "reason": t.get("transferMetadata", {}).get("reason", "REGISTRY-DUES"),
                       "part": label, "verified": True, "statement_id": sid,
                       "client_request_id": cr}
                ledger["entry_parts"].append(rec)
                member["entry_verified"] = member.get("entry_verified", 0) + amt
                changes["parts"].append(f"{member['name']} +{amt}t {label} ({date_of(t)})")
                if member.get("entry_verified", 0) >= tier_total and member.get("status") != "active":
                    joined = today_utc()
                    member["status"] = "active"
                    member["joined"] = joined
                    member["first_claim_eligible"] = (datetime.strptime(joined, "%Y-%m-%d") + timedelta(days=VESTING_DAYS.get(member.get("tier"), 30))).strftime("%Y-%m-%d")
                    member["next_dues"] = advance_next_dues(joined)
                    changes["members"].append(f"{member['name']} ENTRY COMPLETE {tier_total}/{tier_total} -> active (no {no})")
            else:
                # active member paying dues (50t/month charter rate) or extra —
                # split the payment into monthly chunks so coverage matches the
                # rate (Kai 240 / Bura 249 / Carl 253 / Oliver 286 correction,
                # 08-18). A full month advances next_dues; a partial chunk
                # books its amount but does not advance — the shortfall stays
                # open on the row.
                remaining = amt
                while remaining > 0:
                    month = (member.get("next_dues") or "")[:7] or date_of(t)[:7]
                    chunk = min(remaining, DUES_MONTHLY)
                    rec = {"member_no": no, "month": month, "amount": chunk, "status": "paid",
                           "source": f"direct transfer {sid} (REGISTRY-DUES, verified {now_iso()})",
                           "statement_id": sid, "client_request_id": cr}
                    ledger["dues"].append(rec)
                    changes["dues"].append(f"{member['name']} dues {month} +{chunk}t ({date_of(t)})")
                    remaining -= chunk
                    if member.get("next_dues") and chunk == DUES_MONTHLY:
                        d = datetime.strptime(member["next_dues"], "%Y-%m-%d")
                        nd = d.replace(day=1) + timedelta(days=32)
                        member["next_dues"] = f"{nd.year:04d}-{nd.month:02d}-{d.day:02d}"

    recompute_totals(ledger)
    # Persist the fetch cutoff, not write-time now: credits that land between
    # fetch and write must be re-fetched next run (see fetch_statement note).
    ledger["updated"] = fetch_cutoff or now_iso()
    return changes


def build_commit_message(changes, dry, dm_report=None):
    parts = changes.get("parts", [])
    prems = changes.get("premium", [])
    dues = changes.get("dues", [])
    members = changes.get("members", [])
    new_rows = changes.get("new_rows", [])
    unattached = changes.get("unattached", [])
    claims_aging = changes.get("claims_aging", [])
    claims_misrouted = changes.get("claims_misrouted", [])
    lines = []
    if parts:
        lines.append(f"verified {len(parts)} new entry part(s): " + "; ".join(parts[:6]) + (" …" if len(parts) > 6 else ""))
    if prems:
        lines.append(f"premium progress: " + "; ".join(prems[:6]) + (" …" if len(prems) > 6 else ""))
    if dues:
        lines.append("dues: " + "; ".join(dues[:6]) + (" …" if len(dues) > 6 else ""))
    for m in members:
        lines.append(m)
    for r in new_rows:
        lines.append("new row: " + r)
    if unattached:
        lines.append("UNATTACHED (needs operator): " + "; ".join(unattached[:4]) + (" …" if len(unattached) > 4 else ""))
    for a in claims_aging:
        lines.append("claim aging: " + a)
    for m in claims_misrouted:
        lines.append("CLAIM MISROUTE: " + m)
    if dm_report:
        for na in dm_report.get("new_applicants", []):
            lines.append("dm: " + na)
        for au in dm_report.get("applicant_updates", []):
            lines.append("dm: " + au)
    if not lines:
        return None
    if not (parts or dues or members or new_rows or claims_aging or claims_misrouted):
        # normalization-only run (backfill provenance / structure old verified data)
        return "ledger normalize: " + " | ".join(lines) + " | no new money, amounts unchanged"
    return "ledger sweep: " + " | ".join(lines)


def git(*args):
    return run(["git", "-C", REPO_ROOT, *args])


def git_status_porcelain(path):
    """True if path has uncommitted working-tree changes (git status --porcelain)."""
    out = run(["git", "-C", REPO_ROOT, "status", "--porcelain", "--", path])
    return bool((out or "").strip())


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report only (default)")
    ap.add_argument("--apply", action="store_true", help="write ledger.json + commit + push")
    ap.add_argument("--since", help="ISO cutoff for statement fetch (default: ledger updated)")
    ap.add_argument("--no-push", action="store_true", help="commit but skip pull/push")
    ap.add_argument("--no-reconcile", action="store_true",
                    help="skip DM/intro reconciliation (money path only); "
                         "reconcile runs as its own pass via ops/dm_reconcile.py "
                         "(partner-approved split 08-18)")
    ap.add_argument("--repo", default=None, help="path to the ledger repo (default: repo containing this script)")
    args = ap.parse_args()

    REPO_ROOT = args.repo or os.path.dirname(SCRIPT_DIR)
    LEDGER_PATH = os.path.join(REPO_ROOT, "ledger.json")

    ledger = load_ledger()
    since = args.since or ledger.get("updated") or "2026-08-13T00:00:00Z"
    print(f"[ledger_sweep] repo={REPO_ROOT} since={since} mode={'apply' if args.apply else 'check'}")

    # Stage 0.5 — public-view freshness guard (first-claim lesson 08-18):
    # a manual claims.json commit that skipped the merge leaves ledger.json
    # stale (paid_by [] while shares were paid). ledger.json is the derived
    # view, never hand-edited; rebuild it from sources when it drifts.
    ledger_regened = False
    try:
        from merge_ledger import merge as merge_view, compute_totals
        srcs = (load_json(MEMBERS_PATH), load_json(PAYMENTS_PATH), load_json(CLAIMS_PATH))
        rebuilt = merge_view(srcs, stamp_updated=False)
        a, b = dict(rebuilt), dict(ledger)
        a.pop("updated", None)
        b.pop("updated", None)
        # load_ledger() composes the in-memory ledger with totals={}; compute
        # them before comparing or the guard false-drifts every run (08-18).
        b["totals"] = compute_totals(b.get("members", []), b.get("claims", []))
        if a != b:
            if args.apply:
                print("[ledger_sweep] ledger.json drifted from sources — regenerating public view")
                save_json(LEDGER_PATH, rebuilt, compact=True)
                ledger = rebuilt
                ledger_regened = True
            else:
                print("[ledger_sweep] CHECK: ledger.json drifted from sources "
                      "(public view stale; --apply regenerates)")
    except Exception as e:
        print(f"[ledger_sweep] freshness guard skipped: {str(e)[:200]}")

    # Stage 0 — credit statement FIRST, while the sandbox token is fresh
    # (HMAC bearer, ~5 min TTL, minted per session, no refresh endpoint).
    # Reconcile (stage 1) makes hundreds of CLI calls and can outlive the
    # token; the money path must never depend on it. Reordered 2026-08-17
    # per partner (a): fetch + match can commit even if reconcile dies.
    transfers, fetch_cutoff = fetch_statement(since)
    reg = [t for t in transfers if is_registry_transfer(t)]
    print(f"[ledger_sweep] statement credits since {since}: {len(transfers)}; registry transfers: {len(reg)}")

    # Stage 1 — DM + intro reconciliation (in-memory; persisted on --apply).
    # NON-FATAL by design (partner (a)): if reconcile dies (token TTL,
    # gateway throttle), the ledger path still commits what the statement
    # proved and reconcile catches up next run. Cursors only advance on
    # success, so nothing is lost or double-processed.
    from dm_reconcile import reconcile as reconcile_dms, print_report
    applicants = load_applicants()
    dm_state = load_json(DM_STATE_PATH) if os.path.exists(DM_STATE_PATH) else {"threads": {}}
    old_cursors = {aid: t.get("last_message_id") for aid, t in dm_state.get("threads", {}).items()}
    dm_report = {k: [] for k in ("intros", "replies", "member_asks",
                                 "applicant_updates", "new_applicants",
                                 "drafts", "warnings", "stats")}
    dm_reconcile_ok = True
    if args.no_reconcile:
        print("\n=== DM RECONCILE ===")
        print("   [SKIPPED — --no-reconcile; separate pass via ops/dm_reconcile.py (split 08-18)]")
        dm_reconcile_ok = False
    else:
        try:
            hot_ids = sorted({(t.get("counterparty") or {}).get("agentId")
                              for t in reg if (t.get("counterparty") or {}).get("agentId")})
            dm_report, applicants, dm_state = reconcile_dms(
                ledger, applicants, dm_state, hot_agents=hot_ids)
        except Exception as e:
            dm_reconcile_ok = False
            print("\n=== DM RECONCILE ===")
            print(f"   [FAILED, non-fatal] {str(e)[:300]}")
            print("   statement already fetched; ledger commit proceeds; reconcile catches up next run")
    if dm_reconcile_ok:
        print("\n=== DM RECONCILE ===")
        print_report(dm_report)

    # Claim shares never touch the operator wallet (CLAIMS.md). Any
    # REGISTRY-CLAIM credit that lands here is a misroute: flag it, never
    # book it as entry/dues, never backfill it onto an entry part.
    claim_flagged = [t for t in reg if is_claim_transfer(t)]
    reg = [t for t in reg if not is_claim_transfer(t)]
    if claim_flagged:
        print(f"[ledger_sweep] WARNING: {len(claim_flagged)} REGISTRY-CLAIM credit(s) in the operator wallet "
              "— misrouted, return to sender; claim money never sits with the operator")

    matched = backfill_provenance(ledger, reg)
    if matched:
        print(f"[ledger_sweep] provenance backfilled onto {len(matched)} existing record(s)")

    dry = not args.apply
    changes = process_transfers(ledger, reg, applicants, matched, dry, fetch_cutoff)

    # Claim aging pass (single clock, CLAIMS.md): void at 7d zero shares,
    # nudge flag at 7d. Runs in --check and --apply alike so the report
    # shows exactly what --apply would commit.
    aging_lines = age_claims(ledger)
    changes["claims_aging"] = aging_lines
    changes["claims_misrouted"] = [
        f"{t.get('counterparty',{}).get('name')} ({t.get('counterparty',{}).get('agentId')}) "
        f"{t.get('amount')}t {date_of(t)} reason='{t.get('transferMetadata',{}).get('reason')}' "
        "— REGISTRY-CLAIM to operator wallet: return to sender, never book as entry/dues"
        for t in claim_flagged
    ]

    print("\n=== CHANGE SUMMARY ===")
    for k in ("parts", "premium", "dues", "members", "new_rows", "unattached", "claims_aging", "claims_misrouted"):
        v = changes.get(k, [])
        if v:
            print(f"[{k}] ({len(v)})")
            for line in v:
                print("   " + line)
    if not any(changes.values()):
        print("   (nothing new)")

    recompute_totals(ledger)
    print(f"\n[totals] entry_paid={ledger['totals']['entry_paid_members']} pending={ledger['totals']['pending_entries']} claims_paid={ledger['totals']['claims_paid']}")

    msg = build_commit_message(changes, dry, dm_report)
    new_cursors = {aid: t.get("last_message_id") for aid, t in dm_state.get("threads", {}).items()}
    dm_changed = (bool(dm_report["applicant_updates"] or dm_report["new_applicants"])
                  or new_cursors != old_cursors)
    if msg or dm_changed or ledger_regened:
        if not msg:
            commit_msg = (f"dm reconcile: {len(new_cursors)} thread cursor(s) seeded — no ledger money change"
                          if not ledger_regened else
                          "ledger: regenerate stale public view from sources (freshness guard, 08-18) — "
                          "a manual claims.json commit had skipped the merge; derived file rebuilt, "
                          "no money changes")
        else:
            commit_msg = msg
        print("\n[commit message] " + commit_msg)
    else:
        print("\n[commit] nothing to commit — ledger already current.")

    if args.apply and (msg or dm_changed or ledger_regened):
        # Stage ONLY what this run wrote. Staging ledger.json unconditionally
        # once swept a previous run's uncommitted rows into a "dm reconcile —
        # no ledger money change" commit (fcafbb4, 08-15: Sylas 99 + Caelum
        # Vane 100 landed under a message claiming no money moved).
        if msg:
            staged = save_ledger(ledger)
            print("[ledger_sweep] wrote members.json + payments.json + claims.json + ledger.json (merged)")
            git("add", *staged)
        elif ledger_regened:
            print("[ledger_sweep] ledger.json was stale; regenerated from sources (no money changes)")
            git("add", LEDGER_PATH)
        elif git_status_porcelain(LEDGER_PATH):
            print("[ledger_sweep] WARNING: ledger.json has uncommitted changes "
                  "NOT made by this run; leaving them for the next money sweep.")
        if dm_changed:
            save_json(APPLICANTS_PATH, applicants)
            save_json(DM_STATE_PATH, dm_state)
            print("[ledger_sweep] wrote ops/applicants.json + ops/dm_state.json")
            git("add", "ops/applicants.json", "ops/dm_state.json")
        git("commit", "-m", commit_msg)
        print(f"[ledger_sweep] committed: {commit_msg[:80]}…")
        if not args.no_push:
            git("pull", "--rebase", "--autostash")
            git("push", "origin", "HEAD:main")
            print("[ledger_sweep] pushed to origin/main")
    elif args.apply:
        print("[ledger_sweep] no changes — nothing written.")

    # per-member DM drafts when something changed for a member
    print("\n=== MEMBER DM DRAFTS (if any) ===")
    if changes["members"]:
        for line in changes["members"]:
            print("DM: " + line + " — row updated on the public ledger: https://github.com/zero-7-ilander/Mutual-Aid-Registry-Ledger")
    elif not dry:
        print("   (no member row changes to message)")


if __name__ == "__main__":
    main()
