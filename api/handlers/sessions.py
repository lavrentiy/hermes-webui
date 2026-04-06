"""Session CRUD handlers."""
import json
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs

from api.config import (
    STATE_DIR, SESSION_DIR, DEFAULT_WORKSPACE, DEFAULT_MODEL,
    SESSIONS, SESSIONS_MAX, LOCK,
    load_settings,
)
from api.helpers import require, bad, j, read_body
from api.models import (
    Session, get_session, new_session, all_sessions, title_from,
    _write_session_index, SESSION_INDEX_FILE,
    import_cli_session, get_cli_sessions, get_cli_session_messages,
)


def get_session_detail(handler, parsed):
    sid = parse_qs(parsed.query).get('session_id', [''])[0]
    if not sid:
        return j(handler, {'error': 'session_id is required'}, status=400)
    try:
        s = get_session(sid)
        return j(handler, {'session': s.compact() | {
            'messages': s.messages,
            'tool_calls': getattr(s, 'tool_calls', []),
        }})
    except KeyError:
        # Not a WebUI session -- try CLI store
        msgs = get_cli_session_messages(sid)
        if msgs:
            cli_meta = None
            for cs in get_cli_sessions():
                if cs['session_id'] == sid:
                    cli_meta = cs
                    break
            sess = {
                'session_id': sid,
                'title': (cli_meta or {}).get('title', 'CLI Session'),
                'workspace': (cli_meta or {}).get('workspace', ''),
                'model': (cli_meta or {}).get('model', 'unknown'),
                'message_count': len(msgs),
                'created_at': (cli_meta or {}).get('created_at', 0),
                'updated_at': (cli_meta or {}).get('updated_at', 0),
                'pinned': False,
                'archived': False,
                'project_id': None,
                'profile': (cli_meta or {}).get('profile'),
                'is_cli_session': True,
                'messages': msgs,
                'tool_calls': [],
            }
            return j(handler, {'session': sess})
        return bad(handler, 'Session not found', 404)


def get_sessions_list(handler, parsed):
    webui_sessions = all_sessions()
    settings = load_settings()
    if settings.get('show_cli_sessions'):
        cli = get_cli_sessions()
        webui_ids = {s['session_id'] for s in webui_sessions}
        deduped_cli = [s for s in cli if s['session_id'] not in webui_ids]
    else:
        deduped_cli = []
    merged = webui_sessions + deduped_cli
    merged.sort(key=lambda s: s.get('updated_at', 0) or 0, reverse=True)
    return j(handler, {'sessions': merged, 'cli_count': len(deduped_cli)})


def post_session_new(handler, parsed):
    body = read_body(handler)
    s = new_session(workspace=body.get('workspace'), model=body.get('model'))
    return j(handler, {'session': s.compact() | {'messages': s.messages}})


def post_session_rename(handler, parsed):
    body = read_body(handler)
    try: require(body, 'session_id', 'title')
    except ValueError as e: return bad(handler, str(e))
    try: s = get_session(body['session_id'])
    except KeyError: return bad(handler, 'Session not found', 404)
    s.title = str(body['title']).strip()[:80] or 'Untitled'
    s.save()
    return j(handler, {'session': s.compact()})


def post_session_update(handler, parsed):
    body = read_body(handler)
    try: require(body, 'session_id')
    except ValueError as e: return bad(handler, str(e))
    try: s = get_session(body['session_id'])
    except KeyError: return bad(handler, 'Session not found', 404)
    new_ws = str(Path(body.get('workspace', s.workspace)).expanduser().resolve())
    s.workspace = new_ws; s.model = body.get('model', s.model); s.save()
    from api.workspace import set_last_workspace
    set_last_workspace(new_ws)
    return j(handler, {'session': s.compact() | {'messages': s.messages}})


def post_session_delete(handler, parsed):
    body = read_body(handler)
    sid = body.get('session_id', '')
    if not sid: return bad(handler, 'session_id is required')
    # Delete from WebUI session store
    with LOCK: SESSIONS.pop(sid, None)
    p = SESSION_DIR / f'{sid}.json'
    try: p.unlink(missing_ok=True)
    except Exception: pass
    try: SESSION_INDEX_FILE.unlink(missing_ok=True)
    except Exception: pass
    # Also delete from CLI state.db (for CLI sessions shown in sidebar)
    try:
        from api.models import delete_cli_session
        delete_cli_session(sid)
    except Exception: pass
    return j(handler, {'ok': True})


def post_session_clear(handler, parsed):
    body = read_body(handler)
    try: require(body, 'session_id')
    except ValueError as e: return bad(handler, str(e))
    try: s = get_session(body['session_id'])
    except KeyError: return bad(handler, 'Session not found', 404)
    s.messages = []; s.tool_calls = []; s.title = 'Untitled'; s.save()
    return j(handler, {'ok': True, 'session': s.compact()})


def post_session_truncate(handler, parsed):
    body = read_body(handler)
    try: require(body, 'session_id')
    except ValueError as e: return bad(handler, str(e))
    if body.get('keep_count') is None:
        return bad(handler, 'Missing required field(s): keep_count')
    try: s = get_session(body['session_id'])
    except KeyError: return bad(handler, 'Session not found', 404)
    keep = int(body['keep_count'])
    s.messages = s.messages[:keep]; s.save()
    return j(handler, {'ok': True, 'session': s.compact() | {'messages': s.messages}})


def post_session_pin(handler, parsed):
    body = read_body(handler)
    try: require(body, 'session_id')
    except ValueError as e: return bad(handler, str(e))
    try: s = get_session(body['session_id'])
    except KeyError: return bad(handler, 'Session not found', 404)
    s.pinned = bool(body.get('pinned', True))
    s.save()
    return j(handler, {'ok': True, 'session': s.compact()})


def post_session_archive(handler, parsed):
    body = read_body(handler)
    try: require(body, 'session_id')
    except ValueError as e: return bad(handler, str(e))
    try: s = get_session(body['session_id'])
    except KeyError: return bad(handler, 'Session not found', 404)
    s.archived = bool(body.get('archived', True))
    s.save()
    return j(handler, {'ok': True, 'session': s.compact()})


def post_session_move(handler, parsed):
    body = read_body(handler)
    try: require(body, 'session_id')
    except ValueError as e: return bad(handler, str(e))
    try: s = get_session(body['session_id'])
    except KeyError: return bad(handler, 'Session not found', 404)
    s.project_id = body.get('project_id') or None
    s.save()
    return j(handler, {'ok': True, 'session': s.compact()})


def get_session_export(handler, parsed):
    sid = parse_qs(parsed.query).get('session_id', [''])[0]
    if not sid: return bad(handler, 'session_id is required')
    try: s = get_session(sid)
    except KeyError: return bad(handler, 'Session not found', 404)
    payload = json.dumps(s.__dict__, ensure_ascii=False, indent=2)
    handler.send_response(200)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Disposition', f'attachment; filename="hermes-{sid}.json"')
    handler.send_header('Content-Length', str(len(payload.encode('utf-8'))))
    handler.send_header('Cache-Control', 'no-store')
    handler.end_headers()
    handler.wfile.write(payload.encode('utf-8'))
    return True


def get_sessions_search(handler, parsed):
    qs = parse_qs(parsed.query)
    q = qs.get('q', [''])[0].lower().strip()
    content_search = qs.get('content', ['1'])[0] == '1'
    depth = int(qs.get('depth', ['5'])[0])
    if not q: return j(handler, {'sessions': all_sessions()})
    results = []
    for s in all_sessions():
        title_match = q in (s.get('title') or '').lower()
        if title_match:
            results.append(dict(s, match_type='title'))
            continue
        if content_search:
            try:
                sess = get_session(s['session_id'])
                msgs = sess.messages[:depth] if depth else sess.messages
                for m in msgs:
                    c = m.get('content') or ''
                    if isinstance(c, list):
                        c = ' '.join(p.get('text', '') for p in c
                                     if isinstance(p, dict) and p.get('type') == 'text')
                    if q in str(c).lower():
                        results.append(dict(s, match_type='content'))
                        break
            except (KeyError, Exception):
                pass
    return j(handler, {'sessions': results, 'query': q, 'count': len(results)})


def post_sessions_cleanup(handler, parsed):
    body = read_body(handler)
    return _handle_sessions_cleanup(handler, body, zero_only=False)


def post_sessions_cleanup_zero(handler, parsed):
    body = read_body(handler)
    return _handle_sessions_cleanup(handler, body, zero_only=True)


def _handle_sessions_cleanup(handler, body, zero_only=False):
    cleaned = 0
    for p in SESSION_DIR.glob('*.json'):
        if p.name.startswith('_'): continue
        try:
            s = Session.load(p.stem)
            if zero_only:
                should_delete = s and len(s.messages) == 0
            else:
                should_delete = s and s.title == 'Untitled' and len(s.messages) == 0
            if should_delete:
                with LOCK: SESSIONS.pop(p.stem, None)
                p.unlink(missing_ok=True)
                cleaned += 1
        except Exception:
            pass
    if SESSION_INDEX_FILE.exists():
        SESSION_INDEX_FILE.unlink(missing_ok=True)
    return j(handler, {'ok': True, 'cleaned': cleaned})


def post_session_import(handler, parsed):
    body = read_body(handler)
    if not body or not isinstance(body, dict):
        return bad(handler, 'Request body must be a JSON object')
    messages = body.get('messages')
    if not isinstance(messages, list):
        return bad(handler, 'JSON must contain a "messages" array')
    title = body.get('title', 'Imported session')
    workspace = body.get('workspace', str(DEFAULT_WORKSPACE))
    model = body.get('model', DEFAULT_MODEL)
    s = Session(
        title=title, workspace=workspace, model=model,
        messages=messages,
        tool_calls=body.get('tool_calls', []),
    )
    s.pinned = body.get('pinned', False)
    with LOCK:
        SESSIONS[s.session_id] = s
        SESSIONS.move_to_end(s.session_id)
        while len(SESSIONS) > SESSIONS_MAX:
            SESSIONS.popitem(last=False)
    s.save()
    return j(handler, {'ok': True, 'session': s.compact() | {'messages': s.messages}})


def post_session_import_cli(handler, parsed):
    """Import a single CLI session into the WebUI store."""
    body = read_body(handler)
    try:
        require(body, 'session_id')
    except ValueError as e:
        return bad(handler, str(e))

    sid = str(body['session_id'])

    # Check if already imported — idempotent
    existing = Session.load(sid)
    if existing:
        return j(handler, {'session': existing.compact() | {
            'messages': existing.messages,
            'is_cli_session': True,
        }, 'imported': False})

    # Fetch messages from CLI store
    msgs = get_cli_session_messages(sid)
    if not msgs:
        return bad(handler, 'Session not found in CLI store', 404)

    # Derive title from first user message
    title = title_from(msgs, 'CLI Session')
    model = 'unknown'

    # Get profile and model from CLI session metadata
    profile = None
    for cs in get_cli_sessions():
        if cs['session_id'] == sid:
            profile = cs.get('profile')
            model = cs.get('model', 'unknown')
            break

    s = import_cli_session(sid, title, msgs, model, profile=profile)
    s.is_cli_session = True
    s._cli_origin = sid
    s.save()
    return j(handler, {
        'session': s.compact() | {
            'messages': msgs,
            'is_cli_session': True,
        },
        'imported': True,
    })
