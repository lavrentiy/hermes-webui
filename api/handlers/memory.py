"""Memory handlers."""
from pathlib import Path

from api.helpers import require, bad, j, read_body


def get_memory(handler, parsed):
    try:
        from api.profiles import get_active_hermes_home
        mem_dir = get_active_hermes_home() / 'memories'
    except ImportError:
        mem_dir = Path.home() / '.hermes' / 'memories'
    mem_file = mem_dir / 'MEMORY.md'
    user_file = mem_dir / 'USER.md'
    memory = mem_file.read_text(encoding='utf-8', errors='replace') if mem_file.exists() else ''
    user = user_file.read_text(encoding='utf-8', errors='replace') if user_file.exists() else ''
    return j(handler, {
        'memory': memory, 'user': user,
        'memory_path': str(mem_file), 'user_path': str(user_file),
        'memory_mtime': mem_file.stat().st_mtime if mem_file.exists() else None,
        'user_mtime': user_file.stat().st_mtime if user_file.exists() else None,
    })


def post_memory_write(handler, parsed):
    body = read_body(handler)
    try: require(body, 'section', 'content')
    except ValueError as e: return bad(handler, str(e))
    try:
        from api.profiles import get_active_hermes_home
        mem_dir = get_active_hermes_home() / 'memories'
    except ImportError:
        mem_dir = Path.home() / '.hermes' / 'memories'
    mem_dir.mkdir(parents=True, exist_ok=True)
    section = body['section']
    if section == 'memory':
        target = mem_dir / 'MEMORY.md'
    elif section == 'user':
        target = mem_dir / 'USER.md'
    else:
        return bad(handler, 'section must be "memory" or "user"')
    target.write_text(body['content'], encoding='utf-8')
    return j(handler, {'ok': True, 'section': section, 'path': str(target)})
