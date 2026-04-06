"""Dispatch-table router for Hermes Web UI."""


class Router:
    def __init__(self):
        self._exact = {}   # (method, path) -> handler_fn
        self._prefix = []  # (method, prefix, handler_fn)

    def get(self, path, handler_fn):
        self._exact[('GET', path)] = handler_fn

    def post(self, path, handler_fn):
        self._exact[('POST', path)] = handler_fn

    def get_prefix(self, prefix, handler_fn):
        self._prefix.append(('GET', prefix, handler_fn))

    def dispatch(self, method, parsed, handler):
        """Returns True if handled, False for 404."""
        fn = self._exact.get((method, parsed.path))
        if fn:
            return fn(handler, parsed)
        for m, prefix, fn in self._prefix:
            if method == m and parsed.path.startswith(prefix):
                return fn(handler, parsed)
        return False
