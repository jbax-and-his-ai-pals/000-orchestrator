"""Pure steering validation. No database or process side effects."""
import datetime as dt
import hashlib
import json

class Conflict(ValueError):
    pass

def version(value):
    raw = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256((raw or '').encode()).hexdigest()

def expect(actual, expected):
    if expected is not None and actual != expected:
        raise Conflict('stale state; refresh and retry')

def reordered(subs, order):
    ids = [s['id'] for s in subs]
    if any(type(x) is not int for x in order) or len(order) != len(ids) or set(order) != set(ids):
        raise ValueError('order must be a complete permutation of stable subtask IDs')
    by_id = {s['id']: s for s in subs}
    if len(by_id) != len(subs):
        raise ValueError('duplicate subtask IDs')
    for pos, s in enumerate(subs):
        if s.get('status') in ('done','doing') and order[pos] != s['id']:
            raise ValueError('done/doing positions are frozen')
    result = [by_id[x] for x in order]
    edges = {}
    for pos, s in enumerate(result):
        deps = s.get('depends_on') if 'depends_on' in s else [p['id'] for p in result[:pos] if p.get('assignee') != 'ide_handoff']
        if not isinstance(deps, list) or any(type(d) is not int or d not in by_id or d == s['id'] for d in deps):
            raise ValueError('invalid dependency')
        edges[s['id']] = deps
    visited, visiting = set(), set()
    def visit(n):
        if n in visiting:
            raise ValueError('effective dependency cycle')
        if n in visited:
            return
        visiting.add(n)
        for d in edges[n]:
            visit(d)
        visiting.remove(n)
        visited.add(n)
    for n in ids:
        visit(n)
    positions = {n:p for p,n in enumerate(order)}
    if any(positions[d] >= positions[n] for n,deps in edges.items() for d in deps):
        raise ValueError('prerequisite must precede dependent')
    return result

def eligibility(init, project, spot, now, due=False, finishing=False):
    """Shared hard exclusions. Caller supplies clock and graceful-finish evidence."""
    if project.get('priority') == 'skip' and not finishing:
        return 'project skipped'
    def active(value):
        try:
            expiry=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
            current=dt.datetime.fromisoformat(now.replace('Z','+00:00'))
            return expiry.tzinfo is not None and current.tzinfo is not None and expiry>current
        except (ValueError,AttributeError): return False
    if init.get('claimed_by') and active(init.get('claim_expires_at')):
        return 'claimed in chat'
    if project.get('focus_by') and active(project.get('focus_until')):
        return 'project focus'
    if spot:
        if init['project_name'] != spot['project'] and not finishing:
            return 'outside spotlight'
        if init['project_name'] == spot['project'] and due:
            return 'handoff due'
    return None


def recent(value, now, seconds):
    """Aware comparison, including mixed UTC/local-offset observations."""
    try:
        at=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        current=dt.datetime.fromisoformat(now.replace('Z','+00:00'))
        return at.tzinfo is not None and current.tzinfo is not None and 0<=(current-at).total_seconds()<seconds
    except (ValueError,AttributeError,TypeError): return False
