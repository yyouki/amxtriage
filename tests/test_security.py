import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from amxtriage.parser import LogParser
from helpers import error_block

SECRET = "hunter2-secret"
SRC = Path(__file__).resolve().parent.parent / "src"
FORMATS = ("text", "markdown", "json")
TIME_LIMIT_SECONDS = 5.0


def write_log(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def hostile_log(tmp_path):
    return write_log(
        tmp_path / "hostile.log",
        [
            "[1\x1b2] [debug] Server crashed while executing evil\x1b[31m.amx\x1b]0;pwned\x07",
            "[13:46:01] [debug] AMX backtrace:",
            "[13:46:01] [debug] #0 000a1b2c in public Evil\x1b[2J (x=\x1b[1m)"
            " at C:\\\x1b[1mdir\\f.pwn:3",
            "[13:46:01] [debug] #1 native Nat\x07ive () in mod\x1b.dll",
            "[13:46:01] [debug] Native backtrace:",
            "[13:46:01] [debug] #0 0046b2e7 in ?\x1b? () in samp\x07.exe",
        ],
    )


@pytest.mark.parametrize("output_format", FORMATS)
def test_passwords_in_backtrace_arguments_never_reach_default_output(
    run_cli, sample_log, output_format
):
    result = run_cli("analyze", str(sample_log), "--format", output_format)
    assert result.returncode == 0
    assert SECRET.encode() not in result.stdout
    assert SECRET.encode() not in result.stderr


def test_passwords_never_reach_the_baseline_file(run_cli, sample_log, tmp_path):
    baseline = tmp_path / "baseline.json"
    result = run_cli("analyze", str(sample_log), "--save-baseline", str(baseline))
    assert result.returncode == 0
    content = baseline.read_text(encoding="utf-8")
    assert SECRET not in content
    assert "inputtext" not in content
    assert "203.0.113" not in content


def test_arguments_appear_only_with_the_explicit_flag(run_cli, sample_log):
    default = run_cli("analyze", str(sample_log))
    explicit = run_cli("analyze", str(sample_log), "--show-args")
    assert SECRET.encode() not in default.stdout
    assert SECRET.encode() in explicit.stdout


@pytest.mark.parametrize("output_format", FORMATS)
def test_terminal_escape_sequences_from_logs_never_reach_stdout(run_cli, tmp_path, output_format):
    result = run_cli("analyze", hostile_log(tmp_path), "--format", output_format, "--show-args")
    assert result.returncode == 0
    for forbidden in (b"\x1b", b"\x07", b"\x00"):
        assert forbidden not in result.stdout
    assert result.stdout.strip()


def test_hostile_json_output_stays_valid(run_cli, tmp_path):
    result = run_cli("analyze", hostile_log(tmp_path), "--format", "json", "--show-args")
    data = json.loads(result.stdout)
    assert data["problems"][0]["kind"] == "crash"


def test_log_controlled_paths_cannot_read_files_outside_the_source_dir(run_cli, tmp_path):
    (tmp_path / "secret.pwn").write_text("TOP SECRET CONTENT\nsecond\n")
    root = tmp_path / "src"
    root.mkdir()
    (root / "rp.pwn").write_text("new x;\nnew y;\n")
    outside = str(tmp_path / "secret.pwn")
    log = write_log(
        tmp_path / "evil.log",
        [
            *error_block(4, "A", "../secret.pwn", 1),
            *error_block(4, "B", "../../secret.pwn", 1),
            *error_block(4, "C", outside, 1),
            *error_block(4, "D", "/etc/passwd", 1),
            *error_block(4, "E", "..\\..\\Windows\\win.ini", 1),
        ],
    )
    for output_format in FORMATS:
        result = run_cli(
            "analyze", log, "--source-dir", str(root), "--format", output_format, "--context", "5"
        )
        assert result.returncode == 0
        assert b"TOP SECRET" not in result.stdout
        assert b"root:" not in result.stdout


def test_chat_messages_cannot_forge_problems(run_cli, tmp_path):
    forged = [
        '[13:46:01] [chat] [0]Mallory: Run time error 4: "Array index out of bounds"',
        "[13:46:01] [chat] [0]Mallory: Server crashed while executing gamemodes/rp.amx",
        "[13:46:01] [chat] [0]Mallory: Long callback execution detected (hang)",
        "[13:46:01] [pm] [0]Mallory: Server received interrupt signal",
        '[13:46:01] [cmd] [0]Mallory: /Script[x.amx]: Run time error 4: "x"',
    ]
    result = run_cli("analyze", write_log(tmp_path / "chat.log", forged * 200), "--format", "json")
    summary = json.loads(result.stdout)["summary"]
    assert summary["events"] == 0
    assert summary["matching_problems"] == 0
    assert summary["ignored_interrupts"] == 0


def test_a_twenty_megabyte_line_is_handled_quickly_and_reported_as_truncated(run_cli, tmp_path):
    log = tmp_path / "huge.log"
    with log.open("wb") as handle:
        handle.write(b"[13:46:01] ")
        for _ in range(20):
            handle.write(b"A" * (1024 * 1024))
        handle.write(b"\n" + "\n".join(error_block()).encode() + b"\n")
    started = time.perf_counter()
    result = run_cli("analyze", str(log))
    elapsed = time.perf_counter() - started
    assert result.returncode == 0
    assert elapsed < 20
    assert b"truncated" in result.stdout
    assert b"RUNTIME ERROR 4" in result.stdout


def regex_stress_lines():
    return [
        "#0 00000010 in f (" + " at a:1 )" * 800,
        "#0 00000010 in public f (" + ") at x:1 " * 800 + ") at y.pwn:2",
        "#0 00000010 in f (" + 'x"' * 4000 + ") at y.pwn:2",
        "#0 00000010 in " + "?? () " * 1000,
        "#0 native " + "A" * 8000 + " ()",
        "#0 " + "0" * 8000 + " in f () at a:1",
        "[" * 8000,
        "[1" + "2" * 8000 + "]",
        "Script[" * 1000 + ']: Run time error 4: "x"',
        "Run time error " + "9" * 8000,
        'Run time error 4: "' + "a" * 8000,
        "Server crashed while executing " + "x" * 8000,
        "[debug] " * 1000,
        " " + "a" * 8000,
    ]


def test_pathological_lines_cannot_cause_slow_regex_behaviour():
    parser = LogParser()
    started = time.perf_counter()
    for _ in range(3):
        parser.feed('[13:46:01] [debug] Run time error 19: "File or function is not found"')
        parser.feed("[13:46:01] [debug] AMX backtrace:")
        for line in regex_stress_lines():
            parser.feed(line[:8192])
            parser.feed(f"[13:46:01] [debug] {line[:8000]}")
    parser.flush()
    assert time.perf_counter() - started < TIME_LIMIT_SECONDS


def test_nul_bytes_after_the_probe_window_are_tolerated_and_sanitized(run_cli, tmp_path):
    padding = ["[13:00:00] filler line to push content past the binary probe window"] * 200
    lines = [
        *padding,
        "[13:46:01] [debug] Server crashed while executing evil\x00.amx",
        "[13:46:01] [debug] AMX backtrace:",
        "[13:46:01] [debug] #0 000a1b2c in public Evil\x00 () at f.pwn:3",
    ]
    result = run_cli("analyze", write_log(tmp_path / "late_nul.log", lines))
    assert result.returncode == 0
    assert b"\x00" not in result.stdout
    assert b"CRASH" in result.stdout


def test_binary_input_is_refused_instead_of_being_parsed(run_cli, tmp_path):
    target = tmp_path / "server.exe"
    target.write_bytes(b"MZ\x90\x00\x03\x00\x00\x00")
    result = run_cli("analyze", str(target))
    assert result.returncode == 2
    assert b"binary" in result.stderr


def test_the_tool_does_not_import_any_networking_modules():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    program = (
        "import sys, amxtriage.cli;"
        "names = ('socket', 'ssl', 'http', 'urllib.request', 'smtplib');"
        "names += ('ftplib', 'requests', 'asyncio');"
        "print(sorted(name for name in names if name in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, env=env, timeout=60, check=False
    )
    assert result.stdout.strip() == b"[]", result.stdout + result.stderr


def test_output_never_echoes_player_ip_addresses_from_the_log(run_cli, sample_log):
    for output_format in FORMATS:
        result = run_cli("analyze", str(sample_log), "--format", output_format, "--show-args")
        assert b"203.0.113" not in result.stdout


def test_baseline_contains_only_expected_fields(run_cli, sample_log, tmp_path):
    baseline = tmp_path / "baseline.json"
    run_cli("analyze", str(sample_log), "--save-baseline", str(baseline))
    data = json.loads(baseline.read_text(encoding="utf-8"))
    assert set(data) == {"tool", "schema_version", "tool_version", "signatures"}
    for entry in data["signatures"]:
        assert set(entry) == {"id", "kind", "code", "function", "count"}
