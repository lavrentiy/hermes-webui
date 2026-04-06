"""Project CRUD handlers."""
import json
import time
import uuid

from api.config import SESSION_DIR
from api.helpers import require, bad, j, read_body
from api.models import get_session, load_projects, save_projects, SESSION_INDEX_FILE


def get_projects(handler, parsed):
    return j(handler, {'projects': load_projects()})


def post_project_create(handler, parsed):
    body = read_body(handler)
    try: require(body, 'name')
    except ValueError as e: return bad(handler, str(e))
    import re as _re
    name = body['name'].strip()[:128]
    if not name: return bad(handler, 'name required')
    color = body.get('color')
    if color and not _re.match(r'^#[0-9a-fA-F]{3,8}$', color):
        return bad(handler, 'Invalid color format')
    projects = load_projects()
    proj = {'project_id': uuid.uuid4().hex[:12], 'name': name, 'color': color, 'created_at': time.time()}
    projects.append(proj)
    save_projects(projects)
    return j(handler, {'ok': True, 'project': proj})


def post_project_rename(handler, parsed):
    body = read_body(handler)
    try: require(body, 'project_id', 'name')
    except ValueError as e: return bad(handler, str(e))
    import re as _re
    projects = load_projects()
    proj = next((p for p in projects if p['project_id'] == body['project_id']), None)
    if not proj: return bad(handler, 'Project not found', 404)
    proj['name'] = body['name'].strip()[:128]
    if 'color' in body:
        color = body['color']
        if color and not _re.match(r'^#[0-9a-fA-F]{3,8}$', color):
            return bad(handler, 'Invalid color format')
        proj['color'] = color
    save_projects(projects)
    return j(handler, {'ok': True, 'project': proj})


def post_project_delete(handler, parsed):
    body = read_body(handler)
    try: require(body, 'project_id')
    except ValueError as e: return bad(handler, str(e))
    projects = load_projects()
    proj = next((p for p in projects if p['project_id'] == body['project_id']), None)
    if not proj: return bad(handler, 'Project not found', 404)
    projects = [p for p in projects if p['project_id'] != body['project_id']]
    save_projects(projects)
    # Unassign all sessions that belonged to this project
    if SESSION_INDEX_FILE.exists():
        try:
            index = json.loads(SESSION_INDEX_FILE.read_text(encoding='utf-8'))
            for entry in index:
                if entry.get('project_id') == body['project_id']:
                    try:
                        s = get_session(entry['session_id'])
                        s.project_id = None
                        s.save()
                    except Exception:
                        pass
        except Exception:
            pass
    return j(handler, {'ok': True})
