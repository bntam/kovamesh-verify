"""YAML spec loading and validation for kovamesh-verify.

A spec looks like this:

.. code-block:: yaml

    name: my service smoke checks
    base_url: http://127.0.0.1:8765
    timeout: 5
    checks:
      - name: health endpoint returns ok
        type: http
        url: /health
        method: GET
        expected_status: [200]
        max_latency_ms: 1000
        json_contains:
          status: ok
      - name: migrations applied
        type: command
        command: python3 manage.py check
        expected_exit_code: 0

Validation errors raise :class:`SpecError` with a message that names the
offending check and field, so a bad spec fails fast with a readable error
instead of a traceback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

__all__ = ["Check", "Spec", "SpecError", "load_spec", "validate_spec_dict"]

VALID_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
VALID_TYPES = {"http", "command"}


class SpecError(ValueError):
    """Raised when a spec file is missing, malformed, or invalid."""


@dataclass
class Check:
    """One verification check."""

    name: str
    kind: str  # "http" | "command"
    url: str | None = None
    method: str = "GET"
    expected_status: list[int] = field(default_factory=lambda: [200])
    max_latency_ms: int | None = None
    json_contains: dict[str, Any] = field(default_factory=dict)
    body_contains: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    timeout: float | None = None
    command: str | None = None
    expected_exit_code: int = 0
    body: str | None = None


@dataclass
class Spec:
    """A validated verification spec."""

    name: str
    checks: list[Check]
    base_url: str | None = None
    timeout: float = 10.0
    description: str | None = None


def _fail(where: str, message: str) -> None:
    raise SpecError(f"{where}: {message}")


def _require_str(mapping: dict, key: str, where: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        _fail(where, f"missing or empty required field '{key}' (expected a non-empty string)")
    return value.strip()


def _optional_str(mapping: dict, key: str, where: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        _fail(where, f"field '{key}' must be a string, got {type(value).__name__}")
    return value


def _validate_http_check(raw: dict, where: str, base_url: str | None) -> Check:
    url = _require_str(raw, "url", where)

    method = str(raw.get("method", "GET")).upper()
    if method not in VALID_METHODS:
        _fail(
            where,
            f"bad method '{raw.get('method')}' — expected one of {sorted(VALID_METHODS)}",
        )

    expected_status = raw.get("expected_status", [200])
    if isinstance(expected_status, int):
        expected_status = [expected_status]
    if (
        not isinstance(expected_status, list)
        or not expected_status
        or any(not isinstance(s, int) or not 100 <= s <= 599 for s in expected_status)
    ):
        _fail(
            where,
            "bad 'expected_status' — expected an HTTP status code (100-599) "
            "or a list of them, e.g. expected_status: [200, 201]",
        )

    max_latency_ms = raw.get("max_latency_ms")
    if max_latency_ms is not None and (
        not isinstance(max_latency_ms, int) or isinstance(max_latency_ms, bool) or max_latency_ms <= 0
    ):
        _fail(where, "bad 'max_latency_ms' — expected a positive integer (milliseconds)")

    json_contains = raw.get("json_contains", {})
    if not isinstance(json_contains, dict):
        _fail(where, "bad 'json_contains' — expected a mapping of JSON path to expected value")

    body_contains = _optional_str(raw, "body_contains", where)
    body = _optional_str(raw, "body", where)

    headers = raw.get("headers", {})
    if not isinstance(headers, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in headers.items()
    ):
        _fail(where, "bad 'headers' — expected a mapping of string to string")

    timeout = raw.get("timeout")
    if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
        _fail(where, "bad 'timeout' — expected a positive number of seconds")

    if not url.startswith(("http://", "https://")):
        if base_url is None:
            _fail(
                where,
                f"url '{url}' is relative but the spec has no 'base_url' — "
                "set a top-level base_url or use a full http(s) URL",
            )
        if not url.startswith("/"):
            _fail(where, f"url '{url}' must start with '/' when using base_url")

    return Check(
        name=raw["name"],
        kind="http",
        url=url,
        method=method,
        expected_status=list(expected_status),
        max_latency_ms=max_latency_ms,
        json_contains=json_contains,
        body_contains=body_contains,
        headers=headers,
        timeout=float(timeout) if timeout is not None else None,
        body=body,
    )


def _validate_command_check(raw: dict, where: str) -> Check:
    command = _require_str(raw, "command", where)
    expected_exit_code = raw.get("expected_exit_code", 0)
    if (
        not isinstance(expected_exit_code, int)
        or isinstance(expected_exit_code, bool)
        or not 0 <= expected_exit_code <= 255
    ):
        _fail(
            where,
            "bad 'expected_exit_code' — expected an integer between 0 and 255",
        )
    timeout = raw.get("timeout")
    if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
        _fail(where, "bad 'timeout' — expected a positive number of seconds")
    return Check(
        name=raw["name"],
        kind="command",
        command=command,
        expected_exit_code=expected_exit_code,
        timeout=float(timeout) if timeout is not None else None,
    )


def validate_spec_dict(data: Any) -> Spec:
    """Validate a parsed YAML document and return a :class:`Spec`.

    Raises :class:`SpecError` on the first problem found, with a message
    that names the check and field involved.
    """
    if not isinstance(data, dict):
        _fail("spec", "top level must be a YAML mapping, e.g. 'name: my checks'")
    if "name" not in data or not isinstance(data["name"], str) or not data["name"].strip():
        _fail("spec", "missing or empty required field 'name'")
    name = data["name"].strip()

    base_url = data.get("base_url")
    if base_url is not None and (
        not isinstance(base_url, str) or not base_url.startswith(("http://", "https://"))
    ):
        _fail("spec", "bad 'base_url' — expected a full http(s) URL")

    timeout = data.get("timeout", 10.0)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        _fail("spec", "bad 'timeout' — expected a positive number of seconds")

    description = data.get("description")
    if description is not None and not isinstance(description, str):
        _fail("spec", "bad 'description' — expected a string")

    raw_checks = data.get("checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        _fail("spec", "missing or empty required field 'checks' — expected a non-empty list")

    checks: list[Check] = []
    for i, raw in enumerate(raw_checks):
        where = f"checks[{i}]"
        if not isinstance(raw, dict):
            _fail(where, "each check must be a mapping with 'name' and 'type'")
        if "name" not in raw or not isinstance(raw["name"], str) or not raw["name"].strip():
            _fail(where, "missing or empty required field 'name'")
        where = f"checks[{i}] ({raw['name'].strip()})"

        kind = raw.get("type")
        if kind is None:
            # Infer from the fields present so minimal specs stay readable.
            kind = "command" if "command" in raw else "http" if "url" in raw else None
        if kind not in VALID_TYPES:
            _fail(
                where,
                f"bad or missing 'type' — expected 'http' or 'command', got {kind!r}",
            )
        if kind == "http":
            checks.append(_validate_http_check(raw, where, base_url))
        else:
            checks.append(_validate_command_check(raw, where))

    return Spec(
        name=name,
        checks=checks,
        base_url=base_url.rstrip("/") if base_url else None,
        timeout=float(timeout),
        description=description,
    )


def load_spec(path: str | Path) -> Spec:
    """Load and validate a spec file. Raises :class:`SpecError` on failure."""
    path = Path(path)
    if not path.is_file():
        raise SpecError(f"spec file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecError(f"cannot read spec file {path}: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SpecError(f"invalid YAML in {path}: {exc}") from exc
    if data is None:
        raise SpecError(f"spec file is empty: {path}")
    return validate_spec_dict(data)
