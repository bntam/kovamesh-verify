"""Tiny demo service for kovamesh-verify examples.

Serves the endpoints the example specs check against — no dependencies,
stdlib only. Used by the examples, the test suite, and the CI smoke run.

Usage::

    python3 examples/demo_server.py [PORT]   # default 8765

Endpoints:

- ``GET /``          — HTML page mentioning KovaMesh
- ``GET /health``    — ``{"status": "ok", "version": "0.1.0"}``
- ``GET /api/users`` — ``{"count": 2, "users": [...]}``
- ``POST /api/echo`` — echoes a posted JSON object back
- ``GET /slow``      — responds after a 0.5s delay (latency-budget demo)
- anything else      — 404
"""

from __future__ import annotations

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 8765


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep the demo server quiet
        pass

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, text: str, content_type: str = "text/html") -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/":
            self._send_text(
                200,
                "<html><body><h1>KovaMesh demo service</h1>"
                "<p>Every PR, verified at runtime.</p></body></html>",
            )
        elif self.path == "/health":
            self._send_json(200, {"status": "ok", "version": "0.1.0"})
        elif self.path == "/api/users":
            self._send_json(
                200,
                {
                    "count": 2,
                    "users": [
                        {"id": 1, "name": "William"},
                        {"id": 2, "name": "KovaMesh Bot"},
                    ],
                },
            )
        elif self.path == "/slow":
            time.sleep(0.5)
            self._send_json(200, {"status": "ok", "slow": True})
        else:
            self._send_text(404, "not found", content_type="text/plain")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if self.path == "/api/echo":
            try:
                payload = json.loads(raw) if raw else {}
            except ValueError:
                self._send_json(400, {"error": "invalid JSON"})
                return
            self._send_json(200, payload)
        else:
            self._send_text(404, "not found", content_type="text/plain")


def main(argv: list[str] | None = None) -> int:
    port = int(argv[1]) if argv and len(argv) > 1 else DEFAULT_PORT
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"KovaMesh demo service listening on http://127.0.0.1:{port}")
    print("Endpoints: /  /health  /api/users  POST /api/echo  /slow")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
