#!/usr/bin/env python3
"""dm_reconcile.py — DM + intro reconciliation for the Mutual Aid Registry.

Stage 0 of the ledger sweep (called by ops/ledger_sweep.py). Replaces manual
inbox-reading with a deterministic scan of:

  1. intro requests  (ilands intros, both directions, all statuses)
  2. DM threads      (ilands get-dm-thread) for everyone the registry cares
     about: known applicants (ops/applicants.json), ledger members, and
     registry-relevant leads who sent us an intro we accepted

Output: a report of NEW INTROS, REPLY classifications, nudge candidates, and
ready-to-send drafts. Classification is keyword-based and deterministic — no
LLM in the verification path. Cursor state (ops/dm_state.json) makes reruns
idempotent: each thread records the last message id seen, so a message is
classified exactly once.

Writes nothing itself. ledger_sweep.py persists applicants.json and
dm_state.json on --apply and commits them with the ledger.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)  # sibling module import (ledger_sweep helpers)

from ledger_sweep import now_iso, run  # noqa: E402  (run = bounded subprocess)

# --- CLI auth-failure retry --------------------------------------------------
# The sandbox token is an HMAC bearer minted by the runtime per session
# (~5 min TTL) with NO refresh endpoint, so a truly expired token cannot be
# renewed in-process. The retry exists because 401s under reconcile load are
# often transient (gateway/throttle) and recover on a short backoff. True
# expiry is neutralized upstream: ledger_sweep fetches the statement FIRST
# and treats reconcile failure as non-fatal, so the money path always commits.
AUTH_FAIL_RE = re.compile(
    r"rpc returned 401|UNAUTHORIZED|invalid sandbox token|token expired|"
    r"not authenticated|unauthorized", re.IGNORECASE)
AUTH_RETRY_DELAY = 3.0  # seconds before the single retry
AUTH_DEATH_ABORT = 25  # consecutive auth-failed thread fetches -> token dead, stop


def run_cli(cmd):
    """run() with ONE re-auth retry on auth failure (partner 08-17 (b))."""
    try:
        return run(cmd)
    except RuntimeError as e:
        if not AUTH_FAIL_RE.search(str(e)):
            raise
        time.sleep(AUTH_RETRY_DELAY)
        return run(cmd)

REPO_ROOT = os.path.dirname(SCRIPT_DIR)
APPLICANTS_PATH = os.path.join(SCRIPT_DIR, "applicants.json")
DM_STATE_PATH = os.path.join(SCRIPT_DIR, "dm_state.json")
TEMPLATES_PATH = os.path.join(SCRIPT_DIR, "dm_templates.json")

# --- deterministic classification -------------------------------------------

RE_DECLINE = re.compile(
    r"\b(no thanks?|not for me|i'?m out|decline|not interested|can'?t afford|"
    r"won'?t (be|join)|pass(ing)? on this|not my thing)\b", re.IGNORECASE)
RE_ACCEPT = re.compile(
    r"\bi'?m in\b|\bcount me in\b|\bsign me up\b|\bi want in\b|\bi'?m joining\b|"
    r"\bput my name on\b|\bi want my name on\b|\bi will join\b|\bi'?ll join\b|"
    r"\bwe'?re in\b|\bwant in\b|"
    r"\bdoor'?s? (open|mine)\b|\bi accept\b|\bdeal\b", re.IGNORECASE)
RE_PAYMENT = re.compile(
    r"\b(sent|paid|transferred|just sent|on its? way|first part|part\s*\d|"
    r"\d\s*/\s*3|done,?\s*sent|payment (sent|made))\b", re.IGNORECASE)
RE_QUESTION = re.compile(
    r"\?|where does|how (does|do|long|many)|one question|before i (send|move|pay)|"
    r"which tier|do i (pay|send|need)|can you|is the|what'?s the|when (does|is)|"
    r"does the|is this", re.IGNORECASE)
RE_DONE = re.compile(
    r"\b(thanks?|thank you|got it|received|sounds? good|perfect|works for me|"
    r"roger|understood)\b", re.IGNORECASE)

RE_TIER = re.compile(r"\b(starter|standard|premium)\b", re.IGNORECASE)
RE_TIER_AMOUNT = re.compile(r"tier", re.IGNORECASE)
# accepted leads who ask about entry/terms without picking a tier (e.g. "send
# me the full terms?") still need the walkthrough drafted — Shayna 08-14 sat
# 3.5h because a bare question produced no draft.
RE_TERMS_ASK = re.compile(
    r"\bterms?\b|\bhow (much|do|does|to|many)\b|\bjoin\b|\bentry\b|\btier\b|"
    r"\bstarter\b|\bstandard\b|\bpremium\b|\bpay\b|\bcost\b|\bsign\b|"
    r"\bwalkthrough\b|\bdues\b|\brail\b", re.IGNORECASE)

TIER_ENTRY = {"starter": 250, "standard": 400, "premium": 2000}  # September amendment draft

REGISTRY_HINT = re.compile(
    r"registr|mutual aid|ledger|member|charter|dues|entry", re.IGNORECASE)


def classify_reply(text):
    """Deterministic reply classification. Returns (kind, tier|None)."""
    t = text or ""
    tier = None
    m = RE_TIER.search(t)
    if m:
        tier = m.group(1).lower()
    elif RE_TIER_AMOUNT.search(t):
        for cand in ("2000", "2,000", "2 000"):
            if cand in t:
                tier = "premium"
                break
        else:
            if re.search(r"\b250\b", t):
                tier = "starter"
            elif re.search(r"\b400\b", t):
                tier = "standard"
    if RE_DECLINE.search(t):
        return "decline", tier
    if RE_ACCEPT.search(t):
        return "accept", tier
    if RE_PAYMENT.search(t):
        return "payment", tier
    if RE_QUESTION.search(t):
        return "question", tier
    if RE_DONE.search(t):
        return "done", tier
    return "other", tier


def is_registry_lead(intro_message):
    return bool(REGISTRY_HINT.search(intro_message or ""))


# --- data access -------------------------------------------------------------

def fetch_intros():
    """All intros, both directions, grouped by (direction, status).

    The CLI only returns PENDING intros when no --status is passed, so
    accepted/declined must be queried explicitly or accepted leads (e.g.
    Chase 08-14, Dean 08-14) never join the watch set. (fixed 2026-08-14)
    """
    out = {"incoming": {}, "outgoing": {}}
    for direction in ("incoming", "outgoing"):
        for status in ("pending", "accepted", "declined"):
            raw = json.loads(run_cli(["ilands", "intros",
                                      f"--direction={direction}",
                                      f"--status={status}"]))
            for i in raw.get("data", []):
                st = i.get("status", status)
                out[direction].setdefault(st, []).append(i)
    return out


def fetch_thread(aid):
    raw = json.loads(run_cli(["ilands", "get-dm-thread",
                              f"--other-agent-id={aid}", "--limit=50"]))
    return raw.get("details", {}).get("messages", [])


def load_json(path):
    with open(path) as f:
        return json.load(f)


def load_templates():
    if os.path.exists(TEMPLATES_PATH):
        return load_json(TEMPLATES_PATH)
    return {"max_chars": 400}


def max_msg_id(messages):
    """Highest message id seen in a thread (snowflake ids grow over time)."""
    best = None
    for m in messages:
        mid = m.get("id") or ""
        if mid and (best is None or int(mid) > int(best)):
            best = mid
    return best or "0"


def new_provisional_no(applicants):
    """Next free provisional number: max(used numbers) + 1."""
    used = set()
    for a in applicants.values():
        if a.get("provisional_no"):
            used.add(int(a["provisional_no"]))
    if not used:
        return 1
    return max(used) + 1


# --- main reconcile ----------------------------------------------------------

def _fetch_due(state, cutoff_dt):
    """Cadence fallback: settled thread not fetched since cutoff?"""
    try:
        last = datetime.fromisoformat(
            (state.get("last_fetch") or "").replace("Z", "+00:00"))
        return last < cutoff_dt
    except ValueError:
        return True  # never fetched -> due


def reconcile(ledger, applicants, dm_state, templates=None,
              hot_agents=None, unread_agents=None, cadence_hours=24):
    """Scan intros + threads; return (report, applicants, dm_state).

    Watch set is tiered (partner-approved split 08-18): HOT threads fetch
    every pass (pending intros, accepted leads, stale outgoing, applicants,
    open-ask members, open-claim parties, entry-pending members, agents with
    fresh statement credits). Settled members are COLD: fetched only when
    they have unread messages (unread_agents — the daily read_inbox signal)
    or, without that signal, on a time cadence (cadence_hours). This keeps a
    reconcile pass inside the sandbox token TTL (~5 min).

    report: dict with sections for printing. applicants/dm_state are returned
    possibly-updated (in memory); the caller persists on --apply.
    """
    templates = templates or load_templates()
    max_chars = int(templates.get("max_chars", 400))
    report = {"intros": [], "replies": [], "member_asks": [],
              "applicant_updates": [], "new_applicants": [],
              "drafts": [], "warnings": [], "stats": []}
    pending_drafts = []  # (kind, aid, name) tuples, resolved to text below

    # Reporting window: only surface messages newer than the last scan (or the
    # last 24h on a first scan). The cursor still always advances, so reruns
    # classify exactly once and never re-flood history.
    try:
        window_start = datetime.fromisoformat(
            (dm_state.get("last_scan") or "").replace("Z", "+00:00"))
    except ValueError:
        window_start = datetime.now(timezone.utc) - timedelta(hours=24)

    def in_window(m):
        try:
            ts = datetime.fromisoformat((m.get("created_at") or "").replace("Z", "+00:00"))
        except ValueError:
            return True  # unparseable → surface it (safer to over-report)
        return ts >= window_start

    intros = fetch_intros()

    # 1) watch set — tiered (see docstring). Members need idx/no_idx maps
    #    up front: claim parties and statuses drive hot-ness.
    idx = {m.get("agent_id"): m for m in ledger.get("members", [])}
    no_idx = {str(m.get("member_no")): m.get("agent_id")
              for m in ledger.get("members", [])}
    threads = dm_state.setdefault("threads", {})

    hot = set()
    pending_incoming = intros["incoming"].get("pending", [])
    for i in pending_incoming:
        report["intros"].append(
            f"NEW INCOMING INTRO: {i.get('requesterId')} — "
            f"\"{(i.get('introMessage') or '')[:120]}\" (needs reply)")
        hot.add(i.get("requesterId"))

    accepted_incoming = intros["incoming"].get("accepted", [])
    for i in accepted_incoming:
        # leads only until they have a member row; then member tiering rules
        if is_registry_lead(i.get("introMessage", "")) and i.get("requesterId") not in idx:
            hot.add(i.get("requesterId"))

    # accepted outgoing registry pitches are leads too (they said yes to OUR
    # intro — e.g. Dean 08-14); their threads must be watched for tier picks
    accepted_outgoing = intros["outgoing"].get("accepted", [])
    for i in accepted_outgoing:
        if is_registry_lead(i.get("introMessage", "")) and i.get("targetId") not in idx:
            hot.add(i.get("targetId"))

    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    for i in intros["outgoing"].get("pending", []):
        created = i.get("createdAt", "")
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            dt = None
        if dt and dt < cutoff:
            report["intros"].append(
                f"STALE OUTGOING INTRO: {i.get('targetId')} pending since "
                f"{created[:16]} — nudge candidate")
            hot.add(i.get("targetId"))

    # applicants still in flight (accepted, not yet members) always hot;
    # once they have a member row, member tiering rules them.
    for aid in applicants:
        if aid not in idx:
            hot.add(aid)

    # open-claim parties hot until their claim closes
    for c in ledger.get("claims", []):
        if c.get("status") == "paid":
            continue
        for no in [c.get("member_no")] + [s.get("member_no")
                                          for s in c.get("paid_by", [])]:
            aid = no_idx.get(str(no))
            if aid:
                hot.add(aid)

    # fresh statement credits -> hot (they paid; they likely want the confirm)
    if hot_agents:
        hot |= {a for a in hot_agents if a}

    # members: entry_pending + open-ask always hot; settled active = cold
    cold = set()
    for aid, m in idx.items():
        if m.get("status") != "active":
            hot.add(aid)
        elif threads.get(aid, {}).get("open_ask"):
            hot.add(aid)
        else:
            cold.add(aid)

    unread = set(unread_agents or [])
    if unread_agents is not None:
        extra = sorted(cold & unread)
        skipped = len(cold) - len(extra)
        mode = "unread signal"
    else:
        # Cadence fallback must stay bounded: with a stale global last_scan
        # every settled thread becomes 'due', and a full cold scan blows the
        # ~5min sandbox token TTL mid-pass (3 failed runs 08-19, nothing
        # persisted, last_scan stuck at 08-18 22:47Z). Cap the fallback to
        # the FALLBACK_CAP oldest-due threads per pass; the rest defer.
        FALLBACK_CAP = 30
        cadence_cut = datetime.now(timezone.utc) - timedelta(hours=cadence_hours)
        due = [aid for aid in sorted(cold)
               if _fetch_due(threads.get(aid, {}), cadence_cut)]
        due.sort(key=lambda aid: threads.get(aid, {}).get("last_fetch", ""))
        extra = due[:FALLBACK_CAP]
        deferred = len(due) - len(extra)
        skipped = len(cold) - len(extra)
        mode = (f"cadence fallback (no unread signal, cap {FALLBACK_CAP}, "
                f"{deferred} deferred)")
    report["stats"].append(
        f"watch: {len(hot)} hot, {len(extra)} of {len(cold)} settled fetched, "
        f"{skipped} skipped ({mode})")
    watch = sorted(hot) + extra

    # 2) threads — classify new inbound messages per watched agent
    #    (human user ids surface via intros but have no agent thread rail)
    auth_fail_streak = 0
    for aid in (w for w in watch if w and not str(w).startswith("user_")):
        cursor = threads.get(aid, {}).get("last_message_id", "0")
        try:
            messages = fetch_thread(aid)
        except Exception as e:  # no thread / api hiccup — warn, keep going
            report["warnings"].append(f"thread {aid}: {str(e)[:120]}")
            if AUTH_FAIL_RE.search(str(e)):
                auth_fail_streak += 1
                if auth_fail_streak >= AUTH_DEATH_ABORT:
                    report["warnings"].append(
                        f"aborting thread scan: {auth_fail_streak} consecutive auth "
                        f"failures — sandbox token dead; partial state persists, "
                        f"rest catches up next pass (unread-signal run)")
                    break
            else:
                auth_fail_streak = 0
            continue
        auth_fail_streak = 0
        if not messages:
            continue
        new_inbound = [m for m in messages
                       if not m.get("from_self") and
                       (m.get("id") or "0") > cursor]
        name = next((m.get("from_agent_handle") or m.get("to_agent_handle")
                     for m in messages if m.get("from_agent_handle")), aid)
        member = idx.get(aid)
        asked = False
        for m in sorted(new_inbound, key=lambda x: x.get("created_at", "")):
            kind, tier = classify_reply(m.get("body", ""))
            body = (m.get("body") or "")
            summary = body.replace("\n", " ")[:140]
            show = in_window(m)

            if member is not None:
                # members never become applicants; surface anything that wants
                # an operator answer (questions, premium asks, payment notes)
                if kind == "question" or tier == "premium" or "upgrade" in body.lower():
                    asked = True
                    report["member_asks"].append(
                        f"{kind.upper():8s} {name} ({aid}): {summary}")
                elif show:
                    report["replies"].append(
                        f"{kind.upper():8s} {name} ({aid}): {summary}")
                continue

            if show:
                report["replies"].append(
                    f"{kind.upper():8s} {name} ({aid}): {summary}")

            # applicant-side updates
            app = applicants.get(aid)
            if app is None and kind == "question" and \
                    (tier is not None or RE_TERMS_ASK.search(body)):
                # accepted lead asking about terms/entry (no tier picked yet):
                # draft the walkthrough, but don't register an applicant row
                # until they actually accept a tier.
                pending_drafts.append(("walkthrough", aid, name))
            if kind in ("accept", "payment") or (kind == "question" and tier):
                if app is None and kind == "accept":
                    app = {
                        "name": name,
                        "tier": tier or "starter",
                        "entry_total": TIER_ENTRY.get(tier, 300),
                        "provisional_no": new_provisional_no(applicants),
                        "terms_sent": None,
                        "note": (f"auto-registered by dm_reconcile {now_iso()} "
                                 f"(accepted in DM)"),
                    }
                    applicants[aid] = app
                    report["new_applicants"].append(
                        f"{name} ({aid}) → applicant, provisional "
                        f"{app['provisional_no']}, tier {app['tier']}")
                    pending_drafts.append(("walkthrough", aid, name))
                if app is not None:
                    if tier and app.get("tier") != tier:
                        app["tier"] = tier
                        app["entry_total"] = TIER_ENTRY.get(tier, app.get("entry_total", 300))
                        report["applicant_updates"].append(
                            f"{name}: tier → {tier} ({app['entry_total']}t)")
                    if kind == "accept" and not app.get("terms_sent"):
                        pending_drafts.append(("walkthrough", aid, name))

        # open-ask tracking (heuristic): a question/premium/upgrade message
        # reopens the ask; my own latest reply closes it. Drives hot-tiering
        # only — the member_asks report remains the operator's actual queue.
        latest = max(messages, key=lambda x: x.get("created_at") or "") if messages else None
        latest_from_self = bool(latest and latest.get("from_self"))
        open_ask = threads.get(aid, {}).get("open_ask", False)
        if latest_from_self:
            open_ask = False
        else:
            open_ask = open_ask or asked
        threads[aid] = {"last_message_id": max_msg_id(messages),
                        "last_scan": now_iso(), "last_fetch": now_iso(),
                        "open_ask": open_ask}

    # 3) drafts from templates (dedupe, enforce max_chars)
    seen_drafts = set()
    for kind, aid, name in pending_drafts:
        key = (kind, aid)
        if key in seen_drafts:
            continue
        seen_drafts.add(key)
        text = templates.get(kind, "")
        if not text:
            report["warnings"].append(f"no template for draft kind '{kind}'")
            continue
        flag = "" if len(text) <= max_chars else \
            f" !! {len(text)} > {max_chars} chars — WILL TRUNCATE"
        report["drafts"].append(
            f"[{kind} → {name} ({aid})] ({len(text)}/{max_chars} chars{flag})\n{text}")

    dm_state["last_scan"] = now_iso()
    return report, applicants, dm_state


# --- shared printing + standalone pass ---------------------------------------

def print_report(report):
    for section, title in (("intros", "INTROS"), ("replies", "REPLIES"),
                           ("member_asks", "MEMBER ASKS (need operator)"),
                           ("applicant_updates", "APPLICANT UPDATES"),
                           ("new_applicants", "NEW APPLICANTS"),
                           ("warnings", "WARNINGS"), ("stats", "STATS")):
        if report.get(section):
            print(f"[{title}]")
            for line in report[section]:
                print("   " + line)
    if report.get("drafts"):
        print("[DRAFTS — ready to send, copy verbatim]")
        for d in report["drafts"]:
            print("   ---")
            print("   " + d.replace("\n", "\n   "))
    substantive = any(report.get(k) for k in
                      ("intros", "replies", "member_asks", "applicant_updates",
                       "new_applicants", "warnings", "drafts"))
    if not substantive:
        print("   (nothing new)")


def main():
    """Standalone reconcile pass (partner-approved split 08-18).

    The money sweep runs --no-reconcile; this pass owns DM/intro
    reconciliation on its own clock, with a tiered watch set sized to fit
    the sandbox token TTL. Typical daily call:
      python3 ops/dm_reconcile.py --apply --unread-ids=<csv from read_inbox>
    """
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report only (default)")
    ap.add_argument("--apply", action="store_true",
                    help="persist applicants.json + dm_state.json, commit, push")
    ap.add_argument("--hot-ids", help="comma-separated agent ids (fresh statement credits)")
    ap.add_argument("--unread-ids",
                    help="comma-separated agent ids with unread DMs (read_inbox); "
                         "settled members outside this set are skipped this pass")
    ap.add_argument("--no-push", action="store_true", help="commit but skip pull/push")
    ap.add_argument("--repo", default=None, help="path to the ledger repo (default: parent of ops/)")
    args = ap.parse_args()

    REPO = os.path.abspath(args.repo or os.path.dirname(SCRIPT_DIR))
    ledger = load_json(os.path.join(REPO, "ledger.json"))
    applicants = load_json(APPLICANTS_PATH) if os.path.exists(APPLICANTS_PATH) else {}
    dm_state = load_json(DM_STATE_PATH) if os.path.exists(DM_STATE_PATH) else {"threads": {}}

    hot = [x.strip() for x in (args.hot_ids or "").split(",") if x.strip()]
    unread = None
    if args.unread_ids is not None:
        unread = [x.strip() for x in args.unread_ids.split(",") if x.strip()]

    report, applicants, dm_state = reconcile(
        ledger, applicants, dm_state, hot_agents=hot, unread_agents=unread)
    print_report(report)

    if args.apply:
        with open(APPLICANTS_PATH, "w", encoding="utf-8") as f:
            json.dump(applicants, f, ensure_ascii=False, indent=2)
            f.write("\n")
        with open(DM_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(dm_state, f, ensure_ascii=False, indent=2)
            f.write("\n")
        run(["git", "-C", REPO, "add", "ops/applicants.json", "ops/dm_state.json"])
        dirty = run(["git", "-C", REPO, "status", "--porcelain", "--",
                     "ops/applicants.json", "ops/dm_state.json"])
        if (dirty or "").strip():
            n_adv = sum(1 for t in dm_state.get("threads", {}).values()
                        if t.get("last_fetch"))
            msg = (f"dm reconcile: {n_adv} thread(s) advanced, "
                   f"{len(report['drafts'])} draft(s) queued — ops state only")
            run(["git", "-C", REPO, "commit", "-m", msg])
            if not args.no_push:
                run(["git", "-C", REPO, "pull", "--rebase", "origin", "main"])
                run(["git", "-C", REPO, "push", "origin", "main"])
            print(f"[dm_reconcile] committed: {msg}")
        else:
            print("[dm_reconcile] no state changes to commit")
    else:
        print("[dm_reconcile] --check: nothing persisted (run with --apply to commit)")


if __name__ == "__main__":
    main()
