"""Upload handler — delegates directly to api.upload.handle_upload."""
from api.upload import handle_upload as _handle_upload


def post_upload(handler, parsed):
    return _handle_upload(handler)
