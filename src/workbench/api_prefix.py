"""Serve the api under a path prefix as well as at the root.

A shared-host ingress routes only /api to the api, so API paths cannot collide with the UI's page routes.
Work's install serves the api at / on its own host, so the root routes must keep working.
"""


class ApiPrefix:
    def __init__(self, app, prefix: str = "/api"):
        self.app = app
        self.prefix = prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope["path"]
            if path == self.prefix or path.startswith(self.prefix + "/"):
                scope = dict(scope)
                scope["path"] = path[len(self.prefix):] or "/"
                raw = scope.get("raw_path")
                enc = self.prefix.encode()
                if raw is not None and (raw == enc or raw.startswith(enc + b"/") or raw.startswith(enc + b"?")):
                    scope["raw_path"] = raw[len(enc):] or b"/"
        await self.app(scope, receive, send)
