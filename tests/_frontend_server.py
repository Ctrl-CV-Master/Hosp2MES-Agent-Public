"""Minimal SPA static + reverse-proxy server for browser-mode E2E tests.

Serves the prebuilt Vue dist directory on a local port and proxies ``/api/*``
to the Mock MES backend. This avoids spawning a Vite/Node subprocess during
tests, which can be fragile in environments where the workspace is mounted
through a path junction.

The handler implements the two behaviors a Vite preview server provides for
this app:

* ``/api/*``       -> forwarded to ``backend_url`` (forwarding method, headers
                     and body; supports GET / POST / PUT / DELETE).
* everything else -> served from ``dist_dir``. Unknown paths fall back to
                     ``dist/index.html`` so the Vue client-side router handles
                     deep links (e.g. ``/materials``).

Not collected by pytest (leading underscore).
"""
from __future__ import annotations

import http.server
import os
import socketserver
import threading
from urllib.parse import urlparse


class _ProxyHandler(http.server.BaseHTTPRequestHandler):
    backend_url: str = ""
    dist_dir: str = ""

    # Quieter access log.
    def log_message(self, format, *args):  # noqa: A002
        return

    # ---- HTTP dispatch ---------------------------------------------------
    def do_GET(self): self._dispatch()
    def do_POST(self): self._dispatch()
    def do_PUT(self): self._dispatch()
    def do_DELETE(self): self._dispatch()

    def _dispatch(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy_to_backend()
            return
        self._serve_static()

    # ---- /api/* proxy ----------------------------------------------------
    def _proxy_to_backend(self) -> None:
        import httpx

        url = self.backend_url.rstrip("/") + self.path
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        fwd_headers = {k: v for k, v in self.headers.items()
                       if k.lower() not in {"host", "content-length"}}
        try:
            r = httpx.request(self.command, url, headers=fwd_headers,
                              content=body, timeout=30)
            self._write(r.status_code, r.headers, r.content)
        except Exception as exc:  # noqa: BLE001
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            body_out = ('{"detail":"proxy error: %s"}' % exc).encode("utf-8")
            self.send_header("Content-Length", str(len(body_out)))
            self.end_headers()
            self.wfile.write(body_out)

    def _write(self, status: int, headers, body: bytes) -> None:
        self.send_response(status)
        skip = {"content-encoding", "transfer-encoding", "connection"}
        for k, v in headers.items():
            if k.lower() in skip:
                continue
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---- static ----------------------------------------------------------
    def _serve_static(self) -> None:
        path = urlparse(self.path).path
        if path in ("", "/"):
            rel = "index.html"
        else:
            rel = path.lstrip("/")
        # Prevent path traversal.
        full = os.path.normpath(os.path.join(self.dist_dir, rel))
        if not full.startswith(os.path.abspath(self.dist_dir)):
            self.send_error(403)
            return
        if not os.path.isfile(full):
            full = os.path.join(self.dist_dir, "index.html")
        ctype = _content_type(full)
        try:
            with open(full, "rb") as f:
                data = f.read()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".json": "application/json; charset=utf-8",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".map": "application/json; charset=utf-8",
}


def _content_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return _CONTENT_TYPES.get(ext, "application/octet-stream")


class FrontendProxyServer:
    """Threaded HTTP server hosting the prebuilt Vue dist + /api proxy."""

    def __init__(self, dist_dir: str, backend_url: str, port: int):
        self.dist_dir = dist_dir
        self.backend_url = backend_url
        self.port = port

        handler_cls = type(
            "_H",
            (_ProxyHandler,),
            {"backend_url": backend_url, "dist_dir": os.path.abspath(dist_dir)},
        )
        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler_cls)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def serve_forever(self) -> None:
        self._httpd.serve_forever()

    def shutdown(self) -> None:
        try:
            self._httpd.shutdown()
        except Exception:
            pass
        try:
            self._httpd.server_close()
        except Exception:
            pass


def start_frontend_server(dist_dir: str, backend_url: str, port: int) -> FrontendProxyServer:
    """Start a FrontendProxyServer in a background thread and return it."""
    server = FrontendProxyServer(dist_dir, backend_url, port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server