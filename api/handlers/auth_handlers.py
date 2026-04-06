"""Auth handlers: status, login, logout."""
import json

from api.helpers import j, bad, read_body, _security_headers


def get_auth_status(handler, parsed):
    from api.auth import is_auth_enabled, parse_cookie, verify_session
    logged_in = False
    if is_auth_enabled():
        cv = parse_cookie(handler)
        logged_in = bool(cv and verify_session(cv))
    return j(handler, {'auth_enabled': is_auth_enabled(), 'logged_in': logged_in})


def post_login(handler, parsed):
    body = read_body(handler)
    from api.auth import verify_password, create_session, set_auth_cookie, is_auth_enabled
    if not is_auth_enabled():
        return j(handler, {'ok': True, 'message': 'Auth not enabled'})
    password = body.get('password', '')
    if not verify_password(password):
        return bad(handler, 'Invalid password', 401)
    cookie_val = create_session()
    handler.send_response(200)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Cache-Control', 'no-store')
    _security_headers(handler)
    set_auth_cookie(handler, cookie_val)
    handler.end_headers()
    handler.wfile.write(json.dumps({'ok': True}).encode())
    return True


def post_logout(handler, parsed):
    body = read_body(handler)
    from api.auth import clear_auth_cookie, invalidate_session, parse_cookie
    cookie_val = parse_cookie(handler)
    if cookie_val:
        invalidate_session(cookie_val)
    handler.send_response(200)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Cache-Control', 'no-store')
    _security_headers(handler)
    clear_auth_cookie(handler)
    handler.end_headers()
    handler.wfile.write(json.dumps({'ok': True}).encode())
    return True
