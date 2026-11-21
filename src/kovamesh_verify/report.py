"""Human-readable (text table) and machine-readable (JSON) run reports."""

from __future__ import annotations

import json

from .runner import RunResult

__all__ = ["format_json", "format_text", "to_dict"]


def to_dict(result: RunResult) -> dict:
    """Serialise a run result to a plain dict (the ``--format json`` shape)."""
    return {
        "spec": result.spec_name,
        "summary": {
            "passed": result.passed,
            "failed": result.failed,
            "skipped": result.skipped,
            "total": len(result.results),
            "duration_s": round(result.duration_s, 3),
            "ok": result.ok,
        },
        "results": [
            {
                "name": r.name,
                "type": r.kind,
                "status": r.status,
                "latency_ms": round(r.latency_ms, 1) if r.latency_ms is not None else None,
                "detail": r.detail,
            }
            for r in result.results
        ],
    }


def format_json(result: RunResult) -> str:
    return json.dumps(to_dict(result), indent=2)


def format_text(result: RunResult) -> str:
    lines = [f"KovaMesh Verify — {result.spec_name}", ""]
    name_w = max((len(r.name) for r in result.results), default=4)
    rows = [
        f"{'CHECK':<{name_w}}  {'TYPE':<7}  {'STATUS':<6}  {'LATENCY':>8}  DETAIL",
        f"{'-' * name_w}  {'-' * 7}  {'-' * 6}  {'-' * 8}  {'-' * 6}",
    ]
    for r in result.results:
        latency = f"{r.latency_ms:.0f}ms" if r.latency_ms is not None else "-"
        rows.append(
            f"{r.name:<{name_w}}  {r.kind:<7}  {r.status:<6}  {latency:>8}  {r.detail}"
        )
    lines.extend(rows)
    lines.append("")
    lines.append(
        f"{result.passed} passed, {result.failed} failed, {result.skipped} skipped "
        f"({len(result.results)} total, {result.duration_s:.2f}s)"
    )
    return "\n".join(lines)
