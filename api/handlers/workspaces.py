"""Workspace management handlers."""
from pathlib import Path

from api.helpers import bad, j, read_body
from api.workspace import load_workspaces, save_workspaces, get_last_workspace


def get_workspaces(handler, parsed):
    return j(handler, {'workspaces': load_workspaces(), 'last': get_last_workspace()})


def post_workspace_add(handler, parsed):
    body = read_body(handler)
    path_str = body.get('path', '').strip()
    name = body.get('name', '').strip()
    if not path_str: return bad(handler, 'path is required')
    p = Path(path_str).expanduser().resolve()
    if not p.exists(): return bad(handler, f'Path does not exist: {p}')
    if not p.is_dir(): return bad(handler, f'Path is not a directory: {p}')
    wss = load_workspaces()
    if any(w['path'] == str(p) for w in wss):
        return bad(handler, 'Workspace already in list')
    wss.append({'path': str(p), 'name': name or p.name})
    save_workspaces(wss)
    return j(handler, {'ok': True, 'workspaces': wss})


def post_workspace_remove(handler, parsed):
    body = read_body(handler)
    path_str = body.get('path', '').strip()
    if not path_str: return bad(handler, 'path is required')
    wss = load_workspaces()
    wss = [w for w in wss if w['path'] != path_str]
    save_workspaces(wss)
    return j(handler, {'ok': True, 'workspaces': wss})


def post_workspace_rename(handler, parsed):
    body = read_body(handler)
    path_str = body.get('path', '').strip()
    name = body.get('name', '').strip()
    if not path_str or not name: return bad(handler, 'path and name are required')
    wss = load_workspaces()
    for w in wss:
        if w['path'] == path_str:
            w['name'] = name; break
    else:
        return bad(handler, 'Workspace not found', 404)
    save_workspaces(wss)
    return j(handler, {'ok': True, 'workspaces': wss})
