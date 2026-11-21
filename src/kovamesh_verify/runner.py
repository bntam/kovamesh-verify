"""Run a validated spec: HTTP checks and shell-command checks.

Exit-code contract (also used by the CLI):

- ``0`` — every check passed
- ``1`` — at least one check failed
- ``2`` — spec / configuration error (raised as :class:`SpecError` before
  the run starts, so the runner itself never returns 2)
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .spec import Check, Spec

__all__ = ["CheckResult", "RunResult", "run_spec"]

_MISSING = object()


@dataclass
class CheckResult:
    """Outcome of a single check."""

    name: str
    kind: str
    status: str  # "PASS" | "FAIL" | "SKIP"
    latency_ms: float | None = None
    detail: str = ""


@dataclass
class RunResult:
    """Outcome of a whole spec run."""

    spec_name: str
    results: list[CheckResult] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "PASS")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "FAIL")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "SKIP")

    @property
    def ok(self) -> bool:
        return self.failed == 0

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1


def _lookup(data: Any, dotted: str) -> Any:
    """Look up a dotted JSON path (``a.b.0.c``) in parsed JSON data."""
    current: Any = data
    for part in dotted.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return _MISSING
    return current


def _resolve_url(spec: Spec, check: Check) -> str:
    url = check.url or ""
    if url.startswith(("http://", "https://")):
        return url
    return f"{spec.base_url}{url}"


def _run_http(spec: Spec, check: Check, timeout: float) -> CheckResult:
    url = _resolve_url(spec, check)
    data = check.body.encode("utf-8") if check.body is not None else None
    request = urllib.request.Request(url, data=data, method=check.method, headers=check.headers)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            raw_body = response.read()
    except urllib.error.HTTPError as exc:
        # HTTPError still carries the response body — a 404 we expected is
        # a PASS, so treat it like a normal response.
        status = exc.code
        raw_body = exc.read()
        latency_ms = (time.monotonic() - started) * 1000
        return _evaluate_http(check, status, raw_body, latency_ms)
    except Exception as exc:  # connection refused, DNS, timeout, ...
        latency_ms = (time.monotonic() - started) * 1000
        return CheckResult(
            name=check.name,
            kind="http",
            status="FAIL",
            latency_ms=latency_ms,
            detail=f"{type(exc).__name__}: {exc}",
        )
    latency_ms = (time.monotonic() - started) * 1000
    return _evaluate_http(check, status, raw_body, latency_ms)


def _evaluate_http(
    check: Check, status: int, raw_body: bytes, latency_ms: float
) -> CheckResult:
    failures: list[str] = []
    if status not in check.expected_status:
        failures.append(
            f"expected HTTP {check.expected_status}, got {status}"
        )
    if check.max_latency_ms is not None and latency_ms > check.max_latency_ms:
        failures.append(
            f"latency {latency_ms:.0f}ms exceeded max_latency_ms={check.max_latency_ms}ms"
        )
    body_text = raw_body.decode("utf-8", errors="replace")
    if check.body_contains is not None and check.body_contains not in body_text:
        failures.append(f"body did not contain {check.body_contains!r}")
    if check.json_contains:
        try:
            parsed = json.loads(raw_body)
        except (ValueError, UnicodeDecodeError):
            failures.append("body is not valid JSON but 'json_contains' was requested")
            parsed = None
        if parsed is not None:
            for path, expected in check.json_contains.items():
                actual = _lookup(parsed, path)
                if actual is _MISSING:
                    failures.append(f"JSON path {path!r} not found in response")
                elif actual != expected:
                    failures.append(
                        f"JSON path {path!r}: expected {expected!r}, got {actual!r}"
                    )
    if failures:
        return CheckResult(
            name=check.name,
            kind="http",
            status="FAIL",
            latency_ms=latency_ms,
            detail="; ".join(failures),
        )
    return CheckResult(
        name=check.name,
        kind="http",
        status="PASS",
        latency_ms=latency_ms,
        detail=f"HTTP {status}",
    )


def _run_command(spec: Spec, check: Check, timeout: float) -> CheckResult:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            check.command,
            shell=True,  # noqa: S602 - spec files are trusted local input
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        latency_ms = (time.monotonic() - started) * 1000
        return CheckResult(
            name=check.name,
            kind="command",
            status="FAIL",
            latency_ms=latency_ms,
            detail=f"command timed out after {timeout:g}s",
        )
    except Exception as exc:  # e.g. shell itself unavailable
        latency_ms = (time.monotonic() - started) * 1000
        return CheckResult(
            name=check.name,
            kind="command",
            status="FAIL",
            latency_ms=latency_ms,
            detail=f"{type(exc).__name__}: {exc}",
        )
    latency_ms = (time.monotonic() - started) * 1000
    if proc.returncode != check.expected_exit_code:
        detail = (
            f"expected exit code {check.expected_exit_code}, "
            f"got {proc.returncode}"
        )
        stderr = (proc.stderr or "").strip()
        if stderr:
            detail += f" — stderr: {stderr[:200]}"
        return CheckResult(
            name=check.name,
            kind="command",
            status="FAIL",
            latency_ms=latency_ms,
            detail=detail,
        )
    return CheckResult(
        name=check.name,
        kind="command",
        status="PASS",
        latency_ms=latency_ms,
        detail=f"exit code {proc.returncode}",
    )


def run_spec(
    spec: Spec,
    *,
    timeout_override: float | None = None,
    fail_fast: bool = False,
) -> RunResult:
    """Run every check in ``spec`` sequentially and return a :class:`RunResult`.

    With ``fail_fast=True`` the run stops after the first failure and the
    remaining checks are reported as SKIP.
    """
    started = time.monotonic()
    results: list[CheckResult] = []
    for check in spec.checks:
        timeout = (
            timeout_override
            if timeout_override is not None
            else check.timeout if check.timeout is not None
            else spec.timeout
        )
        if check.kind == "http":
            result = _run_http(spec, check, timeout)
        else:
            result = _run_command(spec, check, timeout)
        results.append(result)
        if fail_fast and result.status == "FAIL":
            for remaining in spec.checks[len(results):]:
                results.append(
                    CheckResult(
                        name=remaining.name,
                        kind=remaining.kind,
                        status="SKIP",
                        detail="skipped: --fail-fast stopped the run",
                    )
                )
            break
    return RunResult(
        spec_name=spec.name,
        results=results,
        duration_s=time.monotonic() - started,
    )
