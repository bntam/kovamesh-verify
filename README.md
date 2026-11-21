# kovamesh-verify

[![CI](https://github.com/bntam/kovamesh-verify/actions/workflows/ci.yml/badge.svg)](https://github.com/bntam/kovamesh-verify/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Every PR, verified at runtime.** `kovamesh-verify` runs HTTP and shell-command
health checks from a small YAML spec — the same checks KovaMesh's multi-agent
QA runtime runs against every pull request, deploy, and staging environment.

Static checks (lint, types, unit tests) prove the code compiles. Runtime checks
prove the thing actually works once it is running: the health endpoint answers,
the API returns the shape the frontend expects, the migration command exits
cleanly, the p95 stays inside budget. This CLI is the standalone, open-source
core of that idea.

- **Zero ceremony** — one YAML file, one command, stdlib + PyYAML only.
- **CI-friendly** — exit code `0` when everything passes, `1` on any failure,
  `2` on a bad spec. Text table for humans, `--format json` for machines.
- **No internet required** — the examples run against a bundled local demo
  server, and the test suite spins up its own local HTTP server.

Part of [KovaMesh](https://bntam.github.io/kovamesh/) — multi-agent QA for fast-moving dev
teams. Website: https://bntam.github.io/kovamesh/ (future: kovamesh.dev) · GitHub: https://github.com/bntam/kovamesh-verify

## Install

Requires Python 3.10+.

```bash
pip install kovamesh-verify
# or, from source:
git clone https://github.com/bntam/kovamesh-verify.git
cd kovamesh-verify
pip install -e .
```

## Quickstart

```bash
# 1. Generate a starter spec
kovamesh-verify init

# 2. Validate it (no checks are run)
kovamesh-verify check --spec kovamesh.yaml

# 3. Run it
kovamesh-verify run --spec kovamesh.yaml
```

Example output:

```text
KovaMesh Verify — my service smoke checks

CHECK                        TYPE     STATUS  LATENCY  DETAIL
---------------------------  -------  ------  --------  ------
python is available          command  PASS      12ms  exit code 0

1 passed, 0 failed, 0 skipped (1 total, 0.02s)
```

### Try the bundled examples (local only)

The examples check a demo service that runs on your own machine — nothing
leaves localhost.

```bash
# Terminal 1: start the demo service
python3 examples/demo_server.py 8765

# Terminal 2: run both example specs
kovamesh-verify run --spec examples/kovamesh.yaml
kovamesh-verify run --spec examples/api.yaml --format json
```

## Writing a spec

```yaml
name: my service smoke checks
base_url: http://127.0.0.1:8765   # optional; relative urls resolve against it
timeout: 5                        # default per-check timeout, seconds
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
```

### HTTP checks

| Field | Required | Description |
| --- | --- | --- |
| `name` | yes | Human-readable check name. |
| `type` | yes | `http`. |
| `url` | yes | Full URL, or a path starting with `/` when `base_url` is set. |
| `method` | no | `GET` (default), `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`. |
| `expected_status` | no | Status code or list, e.g. `[200]` (default) or `[200, 201]`. A 404 you expect is a pass. |
| `max_latency_ms` | no | Fail if the response is slower than this (milliseconds). |
| `json_contains` | no | Mapping of dotted JSON path → expected value, e.g. `status: ok`, `users.0.id: 1`. |
| `body_contains` | no | Fail unless the response body contains this string. |
| `headers` | no | Request headers, e.g. `Authorization: Bearer …`. |
| `body` | no | Request body (sent as-is, e.g. a JSON string for POST). |
| `timeout` | no | Per-check timeout in seconds (overrides the spec default). |

### Command checks

| Field | Required | Description |
| --- | --- | --- |
| `name` | yes | Human-readable check name. |
| `type` | yes | `command`. |
| `command` | yes | Shell command to run. |
| `expected_exit_code` | no | Expected exit code, `0` by default. |
| `timeout` | no | Per-check timeout in seconds. |

### Spec-level fields

| Field | Description |
| --- | --- |
| `name` | Spec name (required). |
| `description` | Free text (optional). |
| `base_url` | Base URL for relative check URLs (optional). |
| `timeout` | Default per-check timeout in seconds, `10` by default. |
| `checks` | Non-empty list of checks (required). |

## CLI reference

```bash
kovamesh-verify run --spec FILE [--format text|json] [--timeout SECONDS]
                    [--fail-fast] [--output FILE]
kovamesh-verify check --spec FILE
kovamesh-verify init [--path kovamesh.yaml] [--force]
kovamesh-verify version
```

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | All checks passed (or `check`/`init`/`version` succeeded). |
| `1` | At least one check failed. |
| `2` | Spec error — file not found, invalid YAML, or a validation error. The error message names the check and field. |

`--fail-fast` stops after the first failure and reports the remaining checks
as `SKIP`. `--format json` prints a machine-readable report:

```json
{
  "spec": "my service smoke checks",
  "summary": {"passed": 1, "failed": 0, "skipped": 0, "total": 1, "duration_s": 0.02, "ok": true},
  "results": [
    {"name": "python is available", "type": "command", "status": "PASS", "latency_ms": 12.0, "detail": "exit code 0"}
  ]
}
```

## Development

```bash
pip install -e .[dev]
python -m pytest -q
```

Tests spin up a local HTTP server on an ephemeral port — no internet access
is needed or used.

## Contributing

Issues and pull requests are welcome. Please run `python -m pytest -q` before
submitting, and add a test for any new check type or assertion. See the
[KovaMesh GitHub](https://github.com/bntam) for how the pieces fit
together.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 KovaMesh, William.
