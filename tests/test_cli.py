"""Tests for the CLI (cli.py): exit codes, output shapes, init/version."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from kovamesh_verify import __version__
from kovamesh_verify.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _run_cli(*args, cwd=None):
    """Invoke the CLI the way a user would: python -m kovamesh_verify."""
    return subprocess.run(
        [sys.executable, "-m", "kovamesh_verify", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def test_version(capsys):
    assert main(["version"]) == 0
    assert __version__ in capsys.readouterr().out


def test_check_valid_spec(spec_file, base_url):
    path = spec_file(
        {
            "name": "ok",
            "base_url": base_url,
            "checks": [{"name": "h", "type": "http", "url": "/health"}],
        }
    )
    assert main(["check", "--spec", str(path)]) == 0


def test_check_invalid_spec_exits_2(spec_file, capsys):
    path = spec_file({"name": "bad", "checks": [{"name": "h", "type": "http"}]})
    assert main(["check", "--spec", str(path)]) == 2
    assert "error" in capsys.readouterr().err


def test_cli_run_pass_exits_0(spec_file, base_url):
    path = spec_file(
        {
            "name": "ok",
            "base_url": base_url,
            "checks": [{"name": "h", "type": "http", "url": "/health"}],
        }
    )
    proc = _run_cli("run", "--spec", str(path))
    assert proc.returncode == 0, proc.stderr
    assert "1 passed, 0 failed" in proc.stdout


def test_cli_run_fail_exits_1(spec_file, base_url):
    path = spec_file(
        {
            "name": "bad",
            "base_url": base_url,
            "checks": [
                {"name": "h", "type": "http", "url": "/health", "expected_status": [500]}
            ],
        }
    )
    proc = _run_cli("run", "--spec", str(path))
    assert proc.returncode == 1
    assert "0 passed, 1 failed" in proc.stdout


def test_cli_run_bad_spec_exits_2(spec_file):
    path = spec_file({"name": "bad", "checks": []})
    proc = _run_cli("run", "--spec", str(path))
    assert proc.returncode == 2
    assert "error" in proc.stderr


def test_cli_run_json_output_shape(spec_file, base_url):
    path = spec_file(
        {
            "name": "ok",
            "base_url": base_url,
            "checks": [{"name": "h", "type": "http", "url": "/health"}],
        }
    )
    proc = _run_cli("run", "--spec", str(path), "--format", "json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["spec"] == "ok"
    assert payload["summary"] == {
        "passed": 1,
        "failed": 0,
        "skipped": 0,
        "total": 1,
        "duration_s": payload["summary"]["duration_s"],
        "ok": True,
    }
    assert payload["results"][0]["status"] == "PASS"
    assert payload["results"][0]["type"] == "http"
    assert isinstance(payload["results"][0]["latency_ms"], float)


def test_cli_run_writes_output_file(spec_file, base_url, tmp_path):
    path = spec_file(
        {
            "name": "ok",
            "base_url": base_url,
            "checks": [{"name": "h", "type": "http", "url": "/health"}],
        }
    )
    out = tmp_path / "report.json"
    proc = _run_cli("run", "--spec", str(path), "--format", "json", "--output", str(out))
    assert proc.returncode == 0
    assert json.loads(out.read_text())["summary"]["ok"] is True


def test_init_writes_starter_spec(tmp_path):
    target = tmp_path / "kovamesh.yaml"
    assert main(["init", "--path", str(target)]) == 0
    assert target.exists()
    assert main(["check", "--spec", str(target)]) == 0
    # Second init without --force must refuse to overwrite.
    assert main(["init", "--path", str(target)]) == 2
    assert main(["init", "--path", str(target), "--force"]) == 0


def test_init_spec_runs_and_passes(tmp_path):
    target = tmp_path / "kovamesh.yaml"
    assert main(["init", "--path", str(target)]) == 0
    proc = _run_cli("run", "--spec", str(target), cwd=tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_console_script_exists_and_runs():
    script = shutil.which("kovamesh-verify")
    if script is None:
        pytest.skip("kovamesh-verify console script not on PATH (not installed)")
    proc = subprocess.run(
        [script, "version"], capture_output=True, text=True
    )
    assert proc.returncode == 0
    assert __version__ in proc.stdout


def test_example_kovamesh_spec_passes_end_to_end(base_url):
    """The shipped example runs green against the local demo server."""
    import yaml

    spec = yaml.safe_load((EXAMPLES / "kovamesh.yaml").read_text())
    spec["base_url"] = base_url
    tmp = EXAMPLES / ".test-tmp.yaml"
    tmp.write_text(yaml.safe_dump(spec), encoding="utf-8")
    try:
        proc = _run_cli("run", "--spec", str(tmp))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "5 passed, 0 failed" in proc.stdout
    finally:
        tmp.unlink(missing_ok=True)
