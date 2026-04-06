"""Approval system handlers."""
import threading
from urllib.parse import parse_qs

from api.helpers import bad, j, read_body

# Approval system (optional -- graceful fallback if agent not available)
try:
    from tools.approval import (
        has_pending, pop_pending, submit_pending,
        approve_session, approve_permanent, save_permanent_allowlist,
        is_approved, _pending, _lock, _permanent_approved,
    )
except ImportError:
    has_pending = lambda *a, **k: False
    pop_pending = lambda *a, **k: None
    submit_pending = lambda *a, **k: None
    approve_session = lambda *a, **k: None
    approve_permanent = lambda *a, **k: None
    save_permanent_allowlist = lambda *a, **k: None
    is_approved = lambda *a, **k: True
    _pending = {}
    _lock = threading.Lock()
    _permanent_approved = set()


def get_approval_pending(handler, parsed):
    sid = parse_qs(parsed.query).get('session_id', [''])[0]
    if has_pending(sid):
        with _lock:
            p = dict(_pending.get(sid, {}))
        return j(handler, {'pending': p})
    return j(handler, {'pending': None})


def get_approval_inject_test(handler, parsed):
    """Inject a fake pending approval -- loopback-only, used by automated tests."""
    # Loopback-only: used by automated tests; blocked from any remote client
    if handler.client_address[0] != '127.0.0.1':
        return j(handler, {'error': 'not found'}, status=404)
    qs = parse_qs(parsed.query)
    sid = qs.get('session_id', [''])[0]
    key = qs.get('pattern_key', ['test_pattern'])[0]
    cmd = qs.get('command', ['rm -rf /tmp/test'])[0]
    if sid:
        submit_pending(sid, {
            'command': cmd, 'pattern_key': key,
            'pattern_keys': [key], 'description': 'test pattern',
        })
        return j(handler, {'ok': True, 'session_id': sid})
    return j(handler, {'error': 'session_id required'}, status=400)


def post_approval_respond(handler, parsed):
    body = read_body(handler)
    sid = body.get('session_id', '')
    if not sid: return bad(handler, 'session_id is required')
    choice = body.get('choice', 'deny')
    if choice not in ('once', 'session', 'always', 'deny'):
        return bad(handler, f'Invalid choice: {choice}')
    with _lock:
        pending = _pending.pop(sid, None)
    if pending:
        keys = pending.get('pattern_keys') or [pending.get('pattern_key', '')]
        if choice in ('once', 'session'):
            for k in keys: approve_session(sid, k)
        elif choice == 'always':
            for k in keys:
                approve_session(sid, k); approve_permanent(k)
            save_permanent_allowlist(_permanent_approved)
    return j(handler, {'ok': True, 'choice': choice})
