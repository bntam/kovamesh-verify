"""Command-line interface for kovamesh-verify.

Subcommands:

- ``run``     — run the checks in a spec file (exit 0/1/2)
- ``check``   — validate a spec file without running it (exit 0/2)
- ``init``    — write a starter spec file
- ``version`` — print the version

Exit codes: 0 = all checks passed, 1 = at least one check failed,
2 = spec / configuration error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .report import format_json, format_text
from .runner import run_spec
from .spec import SpecError, load_spec

__all__ = ["STARTER_SPEC", "build_parser", "main"]

STARTER_SPEC = """\
# KovaMesh Verify starter spec — edit the checks, then run:
#   kovamesh-verify run --spec kovamesh.yaml
name: my service smoke checks
# base_url: http://127.0.0.1:8765
timeout: 5
checks:
  - name: python is available
    type: command
    command: python3 --version
    expected_exit_code: 0
  # HTTP checks need a running service. Start the bundled demo server with
  #   python3 examples/demo_server.py 8765
  # then uncomment the checks below and set base_url above.
  # - name: health endpoint returns ok
  #   type: http
  #   url: /health
  #   method: GET
  #   expected_status: [200]
  #   max_latency_ms: 1000
  #   json_contains:
  #     status: ok
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kovamesh-verify",
        description=(
            "Runtime verification for PRs, deploys, and CI — "
            "run HTTP and command health checks from a YAML spec."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the checks in a spec file.")
    run.add_argument("--spec", required=True, help="Path to a YAML spec file.")
    run.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Report format (default: text).",
    )
    run.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Override the per-check timeout in seconds.",
    )
    run.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after the first failing check; skip the rest.",
    )
    run.add_argument(
        "--output",
        default=None,
        help="Write the report to this file instead of stdout.",
    )

    check = sub.add_parser("check", help="Validate a spec file without running it.")
    check.add_argument("--spec", required=True, help="Path to a YAML spec file.")

    init = sub.add_parser("init", help="Write a starter spec file.")
    init.add_argument(
        "--path",
        default="kovamesh.yaml",
        help="Where to write the starter spec (default: kovamesh.yaml).",
    )
    init.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the file if it already exists.",
    )

    sub.add_parser("version", help="Print the version and exit.")
    return parser


def _emit(text: str, output: str | None) -> None:
    if output:
        Path(output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        spec = load_spec(args.spec)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    result = run_spec(spec, timeout_override=args.timeout, fail_fast=args.fail_fast)
    report = format_json(result) if args.format == "json" else format_text(result)
    _emit(report, args.output)
    return result.exit_code


def _cmd_check(args: argparse.Namespace) -> int:
    try:
        spec = load_spec(args.spec)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"spec OK: {spec.name} ({len(spec.checks)} checks)")
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if path.exists() and not args.force:
        print(f"error: {path} already exists (use --force to overwrite)", file=sys.stderr)
        return 2
    path.write_text(STARTER_SPEC, encoding="utf-8")
    print(f"wrote starter spec to {path}")
    print("run it with: kovamesh-verify run --spec " + str(path))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "check":
        return _cmd_check(args)
    if args.command == "init":
        return _cmd_init(args)
    if args.command == "version":
        print(f"kovamesh-verify {__version__}")
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
