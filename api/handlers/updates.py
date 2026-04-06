"""Update check and apply handlers."""
from urllib.parse import parse_qs

from api.config import load_settings
from api.helpers import bad, j, read_body


def get_updates_check(handler, parsed):
    settings = load_settings()
    if not settings.get('check_for_updates', True):
        return j(handler, {'disabled': True})
    qs = parse_qs(parsed.query)
    force = qs.get('force', ['0'])[0] == '1'
    # ?simulate=1 returns fake behind counts for UI testing (localhost only)
    if qs.get('simulate', ['0'])[0] == '1' and handler.client_address[0] == '127.0.0.1':
        return j(handler, {
            'webui': {'name': 'webui', 'behind': 3, 'current_sha': 'abc1234', 'latest_sha': 'def5678', 'branch': 'master'},
            'agent': {'name': 'agent', 'behind': 1, 'current_sha': 'aaa0001', 'latest_sha': 'bbb0002', 'branch': 'master'},
            'checked_at': 0,
        })
    from api.updates import check_for_updates
    return j(handler, check_for_updates(force=force))


def post_updates_apply(handler, parsed):
    body = read_body(handler)
    target = body.get('target', '')
    if target not in ('webui', 'agent'):
        return bad(handler, 'target must be "webui" or "agent"')
    from api.updates import apply_update
    return j(handler, apply_update(target))
