"""File operation handlers: read, raw, delete, save, create, rename, create-dir, list-dir, git-info."""
from pathlib import Path
from urllib.parse import parse_qs

from api.config import MIME_MAP, MAX_FILE_BYTES
from api.helpers import require, bad, safe_resolve, j, read_body
from api.models import get_session
from api.workspace import list_dir, read_file_content


def get_git_info(handler, parsed):
    qs = parse_qs(parsed.query)
    sid = qs.get('session_id', [''])[0]
    if not sid:
        return bad(handler, 'session_id required')
    try:
        s = get_session(sid)
    except KeyError:
        return bad(handler, 'Session not found', 404)
    from api.workspace import git_info_for_workspace
    info = git_info_for_workspace(Path(s.workspace))
    return j(handler, {'git': info})


def get_file(handler, parsed):
    qs = parse_qs(parsed.query)
    sid = qs.get('session_id', [''])[0]
    if not sid: return bad(handler, 'session_id is required')
    try: s = get_session(sid)
    except KeyError: return bad(handler, 'Session not found', 404)
    rel = qs.get('path', [''])[0]
    if not rel: return bad(handler, 'path is required')
    try: return j(handler, read_file_content(Path(s.workspace), rel))
    except (FileNotFoundError, ValueError) as e: return bad(handler, str(e), 404)


def get_file_raw(handler, parsed):
    qs = parse_qs(parsed.query)
    sid = qs.get('session_id', [''])[0]
    if not sid: return bad(handler, 'session_id is required')
    try: s = get_session(sid)
    except KeyError: return bad(handler, 'Session not found', 404)
    rel = qs.get('path', [''])[0]
    force_download = qs.get('download', [''])[0] == '1'
    target = safe_resolve(Path(s.workspace), rel)
    if not target.exists() or not target.is_file():
        return j(handler, {'error': 'not found'}, status=404)
    ext = target.suffix.lower()
    mime = MIME_MAP.get(ext, 'application/octet-stream')
    raw_bytes = target.read_bytes()
    import urllib.parse as _up
    safe_name = _up.quote(target.name, safe='')
    handler.send_response(200)
    handler.send_header('Content-Type', mime)
    handler.send_header('Content-Length', str(len(raw_bytes)))
    handler.send_header('Cache-Control', 'no-store')
    if force_download:
        handler.send_header('Content-Disposition',
            f'attachment; filename="{target.name}"; filename*=UTF-8\'\'{safe_name}')
    handler.end_headers()
    handler.wfile.write(raw_bytes)
    return True


def post_file_delete(handler, parsed):
    body = read_body(handler)
    try: require(body, 'session_id', 'path')
    except ValueError as e: return bad(handler, str(e))
    try: s = get_session(body['session_id'])
    except KeyError: return bad(handler, 'Session not found', 404)
    try:
        target = safe_resolve(Path(s.workspace), body['path'])
        if not target.exists(): return bad(handler, 'File not found', 404)
        if target.is_dir(): return bad(handler, 'Cannot delete directories via this endpoint')
        target.unlink()
        return j(handler, {'ok': True, 'path': body['path']})
    except (ValueError, PermissionError) as e: return bad(handler, str(e))


def post_file_save(handler, parsed):
    body = read_body(handler)
    try: require(body, 'session_id', 'path')
    except ValueError as e: return bad(handler, str(e))
    try: s = get_session(body['session_id'])
    except KeyError: return bad(handler, 'Session not found', 404)
    try:
        target = safe_resolve(Path(s.workspace), body['path'])
        if not target.exists(): return bad(handler, 'File not found', 404)
        if target.is_dir(): return bad(handler, 'Cannot save: path is a directory')
        target.write_text(body.get('content', ''), encoding='utf-8')
        return j(handler, {'ok': True, 'path': body['path'], 'size': target.stat().st_size})
    except (ValueError, PermissionError) as e: return bad(handler, str(e))


def post_file_create(handler, parsed):
    body = read_body(handler)
    try: require(body, 'session_id', 'path')
    except ValueError as e: return bad(handler, str(e))
    try: s = get_session(body['session_id'])
    except KeyError: return bad(handler, 'Session not found', 404)
    try:
        target = safe_resolve(Path(s.workspace), body['path'])
        if target.exists(): return bad(handler, 'File already exists')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body.get('content', ''), encoding='utf-8')
        return j(handler, {'ok': True, 'path': str(target.relative_to(Path(s.workspace)))})
    except (ValueError, PermissionError) as e: return bad(handler, str(e))


def post_file_rename(handler, parsed):
    body = read_body(handler)
    try: require(body, 'session_id', 'path', 'new_name')
    except ValueError as e: return bad(handler, str(e))
    try: s = get_session(body['session_id'])
    except KeyError: return bad(handler, 'Session not found', 404)
    try:
        source = safe_resolve(Path(s.workspace), body['path'])
        if not source.exists(): return bad(handler, 'File not found', 404)
        new_name = body['new_name'].strip()
        if not new_name or '/' in new_name or '..' in new_name:
            return bad(handler, 'Invalid file name')
        dest = source.parent / new_name
        if dest.exists(): return bad(handler, f'A file named "{new_name}" already exists')
        source.rename(dest)
        new_rel = str(dest.relative_to(Path(s.workspace)))
        return j(handler, {'ok': True, 'old_path': body['path'], 'new_path': new_rel})
    except (ValueError, PermissionError, OSError) as e: return bad(handler, str(e))


def post_create_dir(handler, parsed):
    body = read_body(handler)
    try: require(body, 'session_id', 'path')
    except ValueError as e: return bad(handler, str(e))
    try: s = get_session(body['session_id'])
    except KeyError: return bad(handler, 'Session not found', 404)
    try:
        target = safe_resolve(Path(s.workspace), body['path'])
        if target.exists(): return bad(handler, 'Path already exists')
        target.mkdir(parents=True)
        return j(handler, {'ok': True, 'path': str(target.relative_to(Path(s.workspace)))})
    except (ValueError, PermissionError, OSError) as e: return bad(handler, str(e))


def get_list_dir(handler, parsed):
    qs = parse_qs(parsed.query)
    sid = qs.get('session_id', [''])[0]
    if not sid: return bad(handler, 'session_id is required')
    try: s = get_session(sid)
    except KeyError: return bad(handler, 'Session not found', 404)
    try:
        return j(handler, {
            'entries': list_dir(Path(s.workspace), qs.get('path', ['.'])[0]),
            'path': qs.get('path', ['.'])[0],
        })
    except (FileNotFoundError, ValueError) as e:
        return bad(handler, str(e), 404)
