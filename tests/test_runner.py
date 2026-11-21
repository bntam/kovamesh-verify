"""Tests for the check runner (runner.py) against the local demo server."""

from kovamesh_verify.runner import run_spec
from kovamesh_verify.spec import validate_spec_dict


def _spec(base_url, checks, **overrides):
    data = {"name": "t", "base_url": base_url, "checks": checks}
    data.update(overrides)
    return validate_spec_dict(data)


def test_http_200_pass(base_url):
    result = run_spec(_spec(base_url, [{"name": "h", "type": "http", "url": "/health"}]))
    assert result.ok and result.exit_code == 0
    assert result.results[0].status == "PASS"
    assert result.results[0].latency_ms is not None
    assert "200" in result.results[0].detail


def test_wrong_status_fails(base_url):
    result = run_spec(
        _spec(
            base_url,
            [{"name": "h", "type": "http", "url": "/health", "expected_status": [201]}],
        )
    )
    assert not result.ok and result.exit_code == 1
    assert result.results[0].status == "FAIL"
    assert "201" in result.results[0].detail and "200" in result.results[0].detail


def test_expected_404_passes(base_url):
    result = run_spec(
        _spec(
            base_url,
            [{"name": "nf", "type": "http", "url": "/nope", "expected_status": [404]}],
        )
    )
    assert result.ok


def test_latency_threshold_fails(base_url):
    # /slow takes ~500ms; a 100ms budget must fail.
    result = run_spec(
        _spec(
            base_url,
            [{"name": "s", "type": "http", "url": "/slow", "max_latency_ms": 100}],
        )
    )
    assert result.results[0].status == "FAIL"
    assert "latency" in result.results[0].detail


def test_latency_threshold_passes(base_url):
    result = run_spec(
        _spec(
            base_url,
            [{"name": "s", "type": "http", "url": "/slow", "max_latency_ms": 5000}],
        )
    )
    assert result.results[0].status == "PASS"


def test_json_contains_pass(base_url):
    result = run_spec(
        _spec(
            base_url,
            [
                {
                    "name": "j",
                    "type": "http",
                    "url": "/health",
                    "json_contains": {"status": "ok"},
                }
            ],
        )
    )
    assert result.results[0].status == "PASS"


def test_json_contains_wrong_value_fails(base_url):
    result = run_spec(
        _spec(
            base_url,
            [
                {
                    "name": "j",
                    "type": "http",
                    "url": "/health",
                    "json_contains": {"status": "broken"},
                }
            ],
        )
    )
    assert result.results[0].status == "FAIL"
    assert "status" in result.results[0].detail


def test_json_contains_missing_path_fails(base_url):
    result = run_spec(
        _spec(
            base_url,
            [
                {
                    "name": "j",
                    "type": "http",
                    "url": "/health",
                    "json_contains": {"nope": "x"},
                }
            ],
        )
    )
    assert result.results[0].status == "FAIL"


def test_body_contains_pass_and_fail(base_url):
    ok = run_spec(
        _spec(base_url, [{"name": "b", "type": "http", "url": "/", "body_contains": "KovaMesh"}])
    )
    assert ok.results[0].status == "PASS"
    bad = run_spec(
        _spec(base_url, [{"name": "b", "type": "http", "url": "/", "body_contains": "NoSuchText"}])
    )
    assert bad.results[0].status == "FAIL"


def test_post_echo_with_json_assertion(base_url):
    result = run_spec(
        _spec(
            base_url,
            [
                {
                    "name": "e",
                    "type": "http",
                    "url": "/api/echo",
                    "method": "POST",
                    "headers": {"Content-Type": "application/json"},
                    "body": '{"ping": "pong"}',
                    "json_contains": {"ping": "pong"},
                }
            ],
        )
    )
    assert result.results[0].status == "PASS"


def test_connection_refused_is_a_failure_not_a_crash():
    spec = validate_spec_dict(
        {
            "name": "t",
            "checks": [
                {"name": "down", "type": "http", "url": "http://127.0.0.1:1/health"}
            ],
        }
    )
    result = run_spec(spec)
    assert result.results[0].status == "FAIL"
    assert result.exit_code == 1


def test_command_check_pass():
    spec = validate_spec_dict(
        {"name": "t", "checks": [{"name": "c", "type": "command", "command": "echo ok"}]}
    )
    result = run_spec(spec)
    assert result.results[0].status == "PASS"


def test_command_check_wrong_exit_code_fails():
    spec = validate_spec_dict(
        {
            "name": "t",
            "checks": [
                {"name": "c", "type": "command", "command": "exit 3", "expected_exit_code": 0}
            ],
        }
    )
    result = run_spec(spec)
    assert result.results[0].status == "FAIL"
    assert "3" in result.results[0].detail


def test_command_timeout_fails():
    spec = validate_spec_dict(
        {
            "name": "t",
            "checks": [
                {"name": "c", "type": "command", "command": "sleep 5", "timeout": 0.2}
            ],
        }
    )
    result = run_spec(spec)
    assert result.results[0].status == "FAIL"
    assert "timed out" in result.results[0].detail


def test_fail_fast_skips_remaining(base_url):
    result = run_spec(
        _spec(
            base_url,
            [
                {"name": "bad", "type": "http", "url": "/health", "expected_status": [500]},
                {"name": "good", "type": "http", "url": "/health"},
                {"name": "cmd", "type": "command", "command": "true"},
            ],
        ),
        fail_fast=True,
    )
    assert [r.status for r in result.results] == ["FAIL", "SKIP", "SKIP"]
    assert result.failed == 1 and result.skipped == 2


def test_summary_counts(base_url):
    result = run_spec(
        _spec(
            base_url,
            [
                {"name": "a", "type": "http", "url": "/health"},
                {"name": "b", "type": "http", "url": "/health", "expected_status": [500]},
            ],
        )
    )
    assert (result.passed, result.failed, result.skipped) == (1, 1, 0)
