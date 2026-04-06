"""Skills handlers."""
import json
from urllib.parse import parse_qs

from api.helpers import require, bad, j, read_body


def get_skills(handler, parsed):
    from tools.skills_tool import skills_list as _skills_list
    raw = _skills_list()
    data = json.loads(raw) if isinstance(raw, str) else raw
    return j(handler, {'skills': data.get('skills', [])})


def get_skills_content(handler, parsed):
    from tools.skills_tool import skill_view as _skill_view, SKILLS_DIR
    qs = parse_qs(parsed.query)
    name = qs.get('name', [''])[0]
    if not name: return j(handler, {'error': 'name required'}, status=400)
    file_path = qs.get('file', [''])[0]
    if file_path:
        # Serve a linked file from the skill directory
        import re as _re
        if _re.search(r'[*?\[\]]', name):
            return bad(handler, 'Invalid skill name', 400)
        skill_dir = None
        for p in SKILLS_DIR.rglob(name):
            if p.is_dir(): skill_dir = p; break
        if not skill_dir: return bad(handler, 'Skill not found', 404)
        target = (skill_dir / file_path).resolve()
        try: target.relative_to(skill_dir.resolve())
        except ValueError: return bad(handler, 'Invalid file path', 400)
        if not target.exists() or not target.is_file():
            return bad(handler, 'File not found', 404)
        return j(handler, {'content': target.read_text(encoding='utf-8'), 'path': file_path})
    raw = _skill_view(name)
    data = json.loads(raw) if isinstance(raw, str) else raw
    if 'linked_files' not in data: data['linked_files'] = {}
    return j(handler, data)


def post_skill_save(handler, parsed):
    body = read_body(handler)
    try: require(body, 'name', 'content')
    except ValueError as e: return bad(handler, str(e))
    skill_name = body['name'].strip().lower().replace(' ', '-')
    if not skill_name or '/' in skill_name or '..' in skill_name:
        return bad(handler, 'Invalid skill name')
    category = body.get('category', '').strip()
    if category and ('/' in category or '..' in category):
        return bad(handler, 'Invalid category')
    from tools.skills_tool import SKILLS_DIR
    if category:
        skill_dir = SKILLS_DIR / category / skill_name
    else:
        skill_dir = SKILLS_DIR / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / 'SKILL.md'
    skill_file.write_text(body['content'], encoding='utf-8')
    return j(handler, {'ok': True, 'name': skill_name, 'path': str(skill_file)})


def post_skill_delete(handler, parsed):
    body = read_body(handler)
    try: require(body, 'name')
    except ValueError as e: return bad(handler, str(e))
    from tools.skills_tool import SKILLS_DIR
    import shutil
    matches = list(SKILLS_DIR.rglob(f'{body["name"]}/SKILL.md'))
    if not matches: return bad(handler, 'Skill not found', 404)
    skill_dir = matches[0].parent
    shutil.rmtree(str(skill_dir))
    return j(handler, {'ok': True, 'name': body['name']})
