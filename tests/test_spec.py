"""Tests for spec loading and validation (spec.py)."""

import pytest

from kovamesh_verify.spec import SpecError, load_spec, validate_spec_dict


def _valid_http_check(**overrides):
    check = {
        "name": "health",
        "type": "http",
        "url": "/health",
        "expected_status": [200],
    }
    check.update(overrides)
    return check


def test_valid_spec_loads(spec_file):
    path = spec_file(
        {
            "name": "demo",
            "base_url": "http://127.0.0.1:8765",
            "timeout": 5,
            "checks": [_valid_http_check(), {"name": "py", "type": "command", "command": "true"}],
        }
    )
    spec = load_spec(path)
    assert spec.name == "demo"
    assert spec.base_url == "http://127.0.0.1:8765"
    assert spec.timeout == 5
    assert len(spec.checks) == 2
    assert spec.checks[0].kind == "http"
    assert spec.checks[0].method == "GET"
    assert spec.checks[1].kind == "command"


def test_type_is_inferred_from_fields():
    spec = validate_spec_dict(
        {
            "name": "inferred",
            "checks": [
                {"name": "a", "url": "https://example.com/health"},
                {"name": "b", "command": "true"},
            ],
        }
    )
    assert spec.checks[0].kind == "http"
    assert spec.checks[1].kind == "command"


def test_missing_name_errors():
    with pytest.raises(SpecError, match="name"):
        validate_spec_dict({"checks": [_valid_http_check()]})


def test_missing_checks_errors():
    with pytest.raises(SpecError, match="checks"):
        validate_spec_dict({"name": "empty"})


def test_check_missing_url_errors():
    with pytest.raises(SpecError, match="url"):
        validate_spec_dict(
            {"name": "x", "checks": [{"name": "bad", "type": "http"}]}
        )


def test_bad_method_errors():
    with pytest.raises(SpecError, match="bad method"):
        validate_spec_dict(
            {
                "name": "x",
                "checks": [_valid_http_check(method="FETCH")],
            }
        )


def test_bad_status_errors():
    with pytest.raises(SpecError, match="expected_status"):
        validate_spec_dict(
            {
                "name": "x",
                "checks": [_valid_http_check(expected_status=[999])],
            }
        )


def test_relative_url_without_base_url_errors():
    with pytest.raises(SpecError, match="base_url"):
        validate_spec_dict(
            {"name": "x", "checks": [_valid_http_check()]}
        )


def test_bad_check_type_errors():
    with pytest.raises(SpecError, match="type"):
        validate_spec_dict(
            {"name": "x", "checks": [{"name": "bad", "type": "ping"}]}
        )


def test_command_missing_command_errors():
    with pytest.raises(SpecError, match="command"):
        validate_spec_dict(
            {"name": "x", "checks": [{"name": "bad", "type": "command"}]}
        )


def test_missing_spec_file_errors(tmp_path):
    with pytest.raises(SpecError, match="not found"):
        load_spec(tmp_path / "nope.yaml")


def test_invalid_yaml_errors(spec_file):
    path = spec_file({})
    path.write_text("checks: [unclosed\n", encoding="utf-8")
    with pytest.raises(SpecError, match="invalid YAML"):
        load_spec(path)


def test_example_specs_are_valid(base_url):
    """The shipped examples must load — they are what users copy first."""
    from pathlib import Path

    examples = Path(__file__).resolve().parents[1] / "examples"
    for name in ("kovamesh.yaml", "api.yaml"):
        spec = load_spec(examples / name)
        assert spec.checks, f"{name} has no checks"
