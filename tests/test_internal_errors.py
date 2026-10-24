import os
import subprocess
import sys
from pathlib import Path

import pytest

from amxtriage import cli

SRC = Path(__file__).resolve().parent.parent / "src"

FAILING_RUN = (
    "import sys\n"
    "from amxtriage import cli\n"
    "def boom(args):\n"
    "    raise RuntimeError('the text of the error')\n"
    "cli._run_analyze = boom\n"
    "sys.exit(cli.main(['analyze', sys.argv[1], '--baseline', sys.argv[2], '--fail-on-new']))\n"
)


def explode(_args: object) -> int:
    raise RuntimeError("SECRETCONTENT taken from a log line")


def explode_in_depth(_args: object, depth: int = 40) -> int:
    if depth:
        return explode_in_depth(_args, depth - 1)
    raise ValueError("deep")


def explode_with_os_error(_args: object) -> int:
    raise OSError(28, "No space left on device", "/private/secret/report.md")


def explode_with_hostile_names(_args: object) -> int:
    raise RuntimeError("hostile")


def run_main(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_an_unexpected_exception_exits_with_the_error_status(
    monkeypatch: pytest.MonkeyPatch, sample_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "_run_analyze", explode)
    code, out, err = run_main(["analyze", str(sample_log)], capsys)
    assert code == cli.EXIT_ERROR
    assert code != cli.EXIT_NEW_PROBLEMS
    assert out == ""
    assert err.startswith("error: internal error (RuntimeError); please report this as a bug\n")


def test_the_text_of_the_exception_is_never_printed(
    monkeypatch: pytest.MonkeyPatch, sample_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "_run_analyze", explode)
    _, _, err = run_main(["analyze", str(sample_log)], capsys)
    assert "SECRETCONTENT" not in err
    assert "Traceback" not in err


def test_the_place_of_the_failure_is_named_without_directories(
    monkeypatch: pytest.MonkeyPatch, sample_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "_run_analyze", explode)
    _, _, err = run_main(["analyze", str(sample_log)], capsys)
    assert "  at test_internal_errors.py:" in err
    assert " in explode" in err
    assert str(Path(__file__).parent) not in err


def test_only_the_innermost_frames_are_listed(
    monkeypatch: pytest.MonkeyPatch, sample_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "_run_analyze", explode_in_depth)
    _, _, err = run_main(["analyze", str(sample_log)], capsys)
    lines = err.splitlines()
    assert len(lines) == 1 + cli.INTERNAL_ERROR_FRAMES
    assert all(line.startswith("  at ") for line in lines[1:])
    assert lines[-1].endswith(" in explode_in_depth")


def test_the_number_of_listed_frames_is_five() -> None:
    assert cli.INTERNAL_ERROR_FRAMES == 5


def test_an_operating_system_error_names_the_reason_but_not_the_file(
    monkeypatch: pytest.MonkeyPatch, sample_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "_run_analyze", explode_with_os_error)
    code, _, err = run_main(["analyze", str(sample_log)], capsys)
    assert code == cli.EXIT_ERROR
    assert "internal error (OSError: No space left on device)" in err
    assert "/private/secret" not in err


def test_hostile_function_and_file_names_are_sanitized(
    monkeypatch: pytest.MonkeyPatch, sample_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code_object = explode_with_hostile_names.__code__.replace(
        co_filename="dir/evil\x1b[31m\u202e.py", co_name="na\x1bme"
    )
    monkeypatch.setattr(explode_with_hostile_names, "__code__", code_object)
    monkeypatch.setattr(cli, "_run_analyze", explode_with_hostile_names)
    _, _, err = run_main(["analyze", str(sample_log)], capsys)
    assert "\x1b" not in err
    assert "\u202e" not in err
    assert "evil?[31m?.py" in err
    assert " in na?me" in err


def test_a_hostile_exception_class_name_is_sanitized(
    monkeypatch: pytest.MonkeyPatch, sample_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hostile = type("Evil\x1b[31m\u202e", (Exception,), {})

    def raise_hostile(_args: object) -> int:
        raise hostile("text")

    monkeypatch.setattr(cli, "_run_analyze", raise_hostile)
    _, _, err = run_main(["analyze", str(sample_log)], capsys)
    assert "\x1b" not in err
    assert "\u202e" not in err
    assert "internal error (Evil?[31m?)" in err


def test_ordinary_errors_keep_their_plain_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = run_main(["analyze", str(tmp_path / "missing.log")], capsys)
    assert code == cli.EXIT_ERROR
    assert err.startswith("error: cannot open ")
    assert "internal error" not in err


def test_a_program_error_in_watch_is_also_an_internal_error(
    monkeypatch: pytest.MonkeyPatch, sample_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "_run_watch", explode)
    code, _, err = run_main(["watch", str(sample_log)], capsys)
    assert code == cli.EXIT_ERROR
    assert "internal error (RuntimeError)" in err


def test_a_request_for_the_version_still_exits_through_system_exit() -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(["--version"])
    assert caught.value.code == 0


def test_a_keyboard_interrupt_is_not_an_internal_error(
    monkeypatch: pytest.MonkeyPatch, sample_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def interrupted(_args: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_run_analyze", interrupted)
    code, _, err = run_main(["analyze", str(sample_log)], capsys)
    assert code == cli.EXIT_INTERRUPTED
    assert err == ""


def test_the_real_process_does_not_report_a_crash_as_new_problems(
    tmp_path: Path, sample_log: Path
) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text('{"tool": "amxtriage", "schema_version": 1, "signatures": []}')
    environment = {**os.environ, "PYTHONPATH": str(SRC)}
    result = subprocess.run(
        [sys.executable, "-c", FAILING_RUN, str(sample_log), str(baseline)],
        capture_output=True,
        env=environment,
        timeout=120,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"error: internal error (RuntimeError)")
    assert b"the text of the error" not in result.stderr
