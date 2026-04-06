"""Settings handlers."""
from api.config import load_settings, save_settings
from api.helpers import j, read_body


def get_settings(handler, parsed):
    settings = load_settings()
    # Never expose the stored password hash to clients
    settings.pop('password_hash', None)
    return j(handler, settings)


def post_settings(handler, parsed):
    body = read_body(handler)
    saved = save_settings(body)
    saved.pop('password_hash', None)  # never expose hash to client
    return j(handler, saved)
