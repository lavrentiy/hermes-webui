"""Model listing handler."""
from api.config import get_available_models
from api.helpers import j


def get_models(handler, parsed):
    return j(handler, get_available_models())
