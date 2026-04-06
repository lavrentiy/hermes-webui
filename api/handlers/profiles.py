"""Profile handlers."""
from api.helpers import bad, j, read_body


def get_profiles(handler, parsed):
    from api.profiles import list_profiles_api, get_active_profile_name
    return j(handler, {'profiles': list_profiles_api(), 'active': get_active_profile_name()})


def get_profile_active(handler, parsed):
    from api.profiles import get_active_profile_name, get_active_hermes_home
    return j(handler, {'name': get_active_profile_name(), 'path': str(get_active_hermes_home())})


def post_profile_switch(handler, parsed):
    body = read_body(handler)
    name = body.get('name', '').strip()
    if not name: return bad(handler, 'name is required')
    try:
        from api.profiles import switch_profile
        result = switch_profile(name)
        return j(handler, result)
    except (ValueError, FileNotFoundError) as e:
        return bad(handler, str(e), 404)
    except RuntimeError as e:
        return bad(handler, str(e), 409)


def post_profile_create(handler, parsed):
    body = read_body(handler)
    name = body.get('name', '').strip()
    if not name: return bad(handler, 'name is required')
    import re as _re
    if not _re.match(r'^[a-z0-9][a-z0-9_-]{0,63}$', name):
        return bad(handler, 'Invalid profile name: lowercase letters, numbers, hyphens, underscores only')
    clone_from = body.get('clone_from')
    if clone_from is not None:
        clone_from = str(clone_from).strip()
        if not _re.match(r'^[a-z0-9][a-z0-9_-]{0,63}$', clone_from):
            return bad(handler, 'Invalid clone_from name')
    try:
        from api.profiles import create_profile_api
        result = create_profile_api(
            name,
            clone_from=clone_from,
            clone_config=bool(body.get('clone_config', False)),
        )
        return j(handler, {'ok': True, 'profile': result})
    except (ValueError, FileExistsError, RuntimeError) as e:
        return bad(handler, str(e))


def post_profile_delete(handler, parsed):
    body = read_body(handler)
    name = body.get('name', '').strip()
    if not name: return bad(handler, 'name is required')
    try:
        from api.profiles import delete_profile_api
        result = delete_profile_api(name)
        return j(handler, result)
    except (ValueError, FileNotFoundError) as e:
        return bad(handler, str(e))
    except RuntimeError as e:
        return bad(handler, str(e), 409)
