#!/usr/bin/env python3
"""Intro-rail drain for ops/blast_queue.json.

Threadless paid members (no DM thread) can only be reached via send-intro,
capped at 10/24h. Their queued notifications (first-claim, ballot-result,
claim_complete, entry/welcome-complete) accumulate in blast_queue.json.
This script sends ONE welcome intro per unreached member (FIFO by oldest
queued entry), marks ALL of that member's queued entries sent on success,
commits ops-only, pushes. It never touches ledger files or the stamp.

Usage:
  python3 ops/blast_drain.py            # send up to --max (default 10)
  python3 ops/blast_drain.py --dry-run  # print what would be sent, no I/O
  python3 ops/blast_drain.py --max 5    # cap sends this run
"""
import json
import os
import subprocess
import sys
import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(REPO, 'ops', 'blast_queue.json')
LEDGER = os.path.join(REPO, 'ledger.json')
TEMPLATES = os.path.join(REPO, 'ops', 'dm_templates.json')
MAX_SENDS = 10
DRY = '--dry-run' in sys.argv
if '--max' in sys.argv:
    MAX_SENDS = int(sys.argv[sys.argv.index('--max') + 1])

MSG_TEMPLATE_KEY = 'welcome_unreached'


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def main():
    os.chdir(REPO)
    if not DRY:
        run(['git', 'pull', '--rebase', '--quiet'])

    queue = json.load(open(QUEUE, encoding='utf-8'))
    templates = json.load(open(TEMPLATES, encoding='utf-8'))
    template = templates.get(MSG_TEMPLATE_KEY)
    if not template:
        print('FATAL: template', MSG_TEMPLATE_KEY, 'missing from dm_templates.json')
        sys.exit(1)

    # active member numbers from the ledger (welcome only to active members)
    try:
        active = set()
        led = json.load(open(LEDGER, encoding='utf-8'))
        for m in led.get('members', []):
            if m.get('status') == 'active':
                active.add(str(m['member_no']))
    except Exception as e:
        print('WARN: ledger read failed (%s); will not skip by status' % e)
        active = None

    unsent = [e for e in queue if not e.get('sent')]
    by_member = {}
    for e in unsent:
        by_member.setdefault(str(e['member_no']), []).append(e)

    # FIFO by oldest queued entry
    order = sorted(by_member.items(),
                   key=lambda kv: min(e.get('queued', '') for e in kv[1]))

    sent_rows, skipped, failed = [], [], []
    sent_count = 0
    previewed = 0
    for row, entries in order:
        if sent_count >= MAX_SENDS:
            break
        if DRY and previewed >= MAX_SENDS:
            break
        if active is not None and row not in active:
            for e in entries:
                e['sent'] = True
                e['sent_at'] = now_iso()
                e['note'] = 'skipped: not active on ledger'
            skipped.append(row)
            continue
        agent_id = entries[0].get('agent_id')
        if not agent_id:
            failed.append((row, 'no agent_id'))
            continue
        msg = template.format(row=row)
        if DRY:
            print('WOULD INTRO row %s (%s, %s): %s...' % (row, entries[0].get('name'), agent_id, msg[:80]))
            continue
        res = run(['ilands', 'send-intro', '--target-type=agent',
                   '--target-id=%s' % agent_id, '--message=%s' % msg])
        out = res.stdout or res.stderr
        try:
            parsed = json.loads(out)
        except Exception:
            parsed = {}
        if res.returncode == 0 and 'error' not in parsed:
            intro_id = None
            d = parsed.get('data') or {}
            if isinstance(d, dict):
                intro_id = d.get('id')
            for e in entries:
                e['sent'] = True
                e['sent_at'] = now_iso()
                e['note'] = 'intro rail %s' % (intro_id or 'ok')
            sent_rows.append(row)
            sent_count += 1
        elif 'DM_RATE_LIMITED' in out or '429' in out:
            print('cap hit after %d sends; stopping' % sent_count)
            break
        else:
            failed.append((row, (out or 'unknown error')[:120]))

    if DRY:
        print('dry-run: would send %d intro(s); %d skipped (not active); %d problem rows'
              % (min(len(order), MAX_SENDS), len(skipped), len(failed)))
        return

    if not sent_rows and not skipped:
        print('nothing to do')
        return

    with open(QUEUE, 'w', encoding='utf-8') as f:
        json.dump(queue, f, indent=1, ensure_ascii=False)
        f.write('\n')

    run(['git', 'add', 'ops/blast_queue.json'])
    msg = 'ops: intro drain %d rows (%s)%s' % (
        len(sent_rows), ','.join(sent_rows),
        '; %d skipped (not active)' % len(skipped) if skipped else '')
    c = run(['git', 'commit', '-q', '-m', msg])
    if c.returncode != 0:
        print('commit failed:', c.stderr[:300])
    p = run(['git', 'push', '-q', 'origin', 'HEAD'])
    print('drained %d: %s; skipped %d: %s; failed %d: %s' % (
        len(sent_rows), sent_rows, len(skipped), skipped, len(failed), failed[:5]))


if __name__ == '__main__':
    main()
