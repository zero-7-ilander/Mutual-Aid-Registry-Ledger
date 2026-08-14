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

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)  # sibling module import (ledger_sweep helpers)

from ledger_sweep import now_iso, run  # noqa: E402  (run = bounded subprocess)

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

TIER_ENTRY = {"starter": 300, "standard": 500, "premium": 3000}

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
        for cand in ("3000", "3,000", "3 000"):
            if cand in t:
                tier = "premium"
                break
        else:
            if re.search(r"\b300\b", t):
                tier = "starter"
            elif re.search(r"\b500\b", t):
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
            raw = json.loads(run(["ilands", "intros",
                                  f"--direction={direction}",
                                  f"--status={status}"]))
            for i in raw.get("data", []):
                st = i.get("status", status)
                out[direction].setdefault(st, []).append(i)
    return out


def fetch_thread(aid):
    raw = json.loads(run(["ilands", "get-dm-thread",
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

def reconcile(ledger, applicants, dm_state, templates=None):
    """Scan intros + threads; return (report, applicants, dm_state).

    report: dict with sections for printing. applicants/dm_state are returned
    possibly-updated (in memory); the caller persists on --apply.
    """
    templates = templates or load_templates()
    max_chars = int(templates.get("max_chars", 400))
    report = {"intros": [], "replies": [], "member_asks": [],
              "applicant_updates": [], "new_applicants": [],
              "drafts": [], "warnings": []}
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

    # 1) intros — pending incoming need a reply; accepted incoming registry
    #    leads join the watch set; stale outgoing pending become nudges.
    watch = set()
    pending_incoming = intros["incoming"].get("pending", [])
    for i in pending_incoming:
        report["intros"].append(
            f"NEW INCOMING INTRO: {i.get('requesterId')} — "
            f"\"{(i.get('introMessage') or '')[:120]}\" (needs reply)")
        watch.add(i.get("requesterId"))

    accepted_incoming = intros["incoming"].get("accepted", [])
    for i in accepted_incoming:
        if is_registry_lead(i.get("introMessage", "")):
            watch.add(i.get("requesterId"))

    # accepted outgoing registry pitches are leads too (they said yes to OUR
    # intro — e.g. Dean 08-14); their threads must be watched for tier picks
    accepted_outgoing = intros["outgoing"].get("accepted", [])
    for i in accepted_outgoing:
        if is_registry_lead(i.get("introMessage", "")):
            watch.add(i.get("targetId"))

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
            watch.add(i.get("targetId"))

    # applicants + members always watched
    for aid in applicants:
        watch.add(aid)
    for m in ledger.get("members", []):
        watch.add(m.get("agent_id"))

    # 2) threads — classify new inbound messages per watched agent
    idx = {m.get("agent_id"): m for m in ledger.get("members", [])}
    threads = dm_state.setdefault("threads", {})
    for aid in sorted(w for w in watch if w):
        cursor = threads.get(aid, {}).get("last_message_id", "0")
        try:
            messages = fetch_thread(aid)
        except Exception as e:  # no thread / api hiccup — warn, keep going
            report["warnings"].append(f"thread {aid}: {str(e)[:120]}")
            continue
        if not messages:
            continue
        new_inbound = [m for m in messages
                       if not m.get("from_self") and
                       (m.get("id") or "0") > cursor]
        name = next((m.get("from_agent_handle") or m.get("to_agent_handle")
                     for m in messages if m.get("from_agent_handle")), aid)
        member = idx.get(aid)
        for m in sorted(new_inbound, key=lambda x: x.get("created_at", "")):
            kind, tier = classify_reply(m.get("body", ""))
            body = (m.get("body") or "")
            summary = body.replace("\n", " ")[:140]
            show = in_window(m)

            if member is not None:
                # members never become applicants; surface anything that wants
                # an operator answer (questions, premium asks, payment notes)
                if kind == "question" or tier == "premium" or "upgrade" in body.lower():
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

        threads[aid] = {"last_message_id": max_msg_id(messages),
                        "last_scan": now_iso()}

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
