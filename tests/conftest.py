"""Shared fixtures: a local demo HTTP server on an ephemeral port.

No internet access is used anywhere in the test suite — the server is the
same stdlib demo service shipped in ``examples/demo_server.py``.
"""

from __future__ import annotations

import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
sys.path.insert(0, str(EXAMPLES_DIR))

import demo_server  # noqa: E402  (import after sys.path setup)


@pytest.fixture(scope="session")
def base_url():
    """Base URL of a running local demo server."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), demo_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture()
def spec_file(tmp_path):
    """Factory: write a spec dict as YAML, return its path."""

    def _write(data, name="spec.yaml"):
        import yaml

        path = tmp_path / name
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        return path

    return _write
