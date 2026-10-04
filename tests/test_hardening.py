import json
import os
import signal
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path

import pytest

from amxtriage.analysis import analyze_logs, build_report
from amxtriage.baseline import load_baseline
from amxtriage.errors import BaselineError
from amxtriage.parser import MAX_NATIVE_FRAMES
from amxtriage.render import render_json, render_markdown, render_text
from amxtriage.source import SourceIndex
from helpers import error_block, events_of

SRC = Path(__file__).resolve().parent.parent / "src"
BLOCKED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
HOSTILE = "\x1b[31m\x07\u202e\x9b\u200b\x7f"
SECRET = "hunter2-secret"
WAIT_SECONDS = 30.0

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX behaviour only")


def dangerous(text, *, allow_newline=True):
    return sorted(
        {
            char
            for char in text
            if unicodedata.category(char) in BLOCKED_CATEGORIES
            and not (allow_newline and char == "\n")
        }
    )


def json_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from json_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from json_strings(item)


def assert_clean_in_every_format(report):
    for show_args in (False, True):
        for render in (render_text, render_markdown):
            assert dangerous(render(report, show_args=show_args)) == []
        data = json.loads(render_json(report, show_args=show_args))
        for value in json_strings(data):
            assert dangerous(value, allow_newline=False) == [], value


def hostile_lines():
    return [
        f'[13:46:01] [debug] Run time error 4: "msg{HOSTILE}"',
        "[13:46:01] [debug] AMX backtrace:",
        f"[13:46:01] [debug] #0 000a1b2c in public Fn{HOSTILE} (x=1)"
        f" at dir{HOSTILE}/file{HOSTILE}.pwn:3",
        f'[13:46:01] Script[gamemodes/scr{HOSTILE}.amx]: Run time error 4: "msg{HOSTILE}"',
    ]


def test_hostile_runtime_error_fields_are_sanitized_in_every_format(tmp_path):
    log = tmp_path / "hostile.log"
    log.write_text("\n".join(hostile_lines()) + "\n", encoding="utf-8")
    report = build_report(analyze_logs([str(log)]), top=20)
    problem = json.loads(render_json(report))["problems"][0]
    assert problem["message"].startswith("msg")
    assert problem["script"].startswith("gamemodes/scr")
    assert problem["function"].startswith("Fn")
    assert problem["file"].startswith("dir")
    assert_clean_in_every_format(report)


@posix_only
def test_hostile_log_file_names_are_sanitized_in_every_format(tmp_path):
    log = tmp_path / f"evil{HOSTILE}.log"
    try:
        log.write_text("\n".join(error_block()) + "\n", encoding="utf-8")
    except OSError:
        pytest.skip("this file system rejects control characters in file names")
    report = build_report(analyze_logs([str(log)]), top=20)
    assert "evil" in render_text(report)
    assert_clean_in_every_format(report)


@posix_only
def test_hostile_source_file_names_are_sanitized_in_every_format(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    name = f"evil{HOSTILE}.pwn"
    try:
        (root / name).write_text("new a;\nnew b;\nnew c;\n", encoding="utf-8")
    except OSError:
        pytest.skip("this file system rejects control characters in file names")
    log = tmp_path / "server_log.txt"
    log.write_text("\n".join(error_block(4, "Fn", f"gamemodes/{name}", 2)) + "\n", encoding="utf-8")
    report = build_report(
        analyze_logs([str(log)]), top=20, source_index=SourceIndex(str(root)), context_radius=1
    )
    assert len(report.contexts) == 1
    assert_clean_in_every_format(report)


def test_native_backtrace_frame_count_is_capped():
    lines = [
        "[13:46:01] [debug] Server crashed while executing gamemodes/rp.amx",
        "[13:46:01] [debug] Native backtrace:",
        *[f"[13:46:01] [debug] #{n} 0046b2e7 in ?? () in samp-server.exe" for n in range(500)],
    ]
    events = events_of(lines)
    assert len(events) == 1
    assert len(events[0].native_frames) == MAX_NATIVE_FRAMES


@pytest.mark.parametrize("identifier", ["abcdef", "0123456789abcdef0"])
def test_baseline_ids_with_the_wrong_length_are_rejected(tmp_path, identifier):
    path = tmp_path / "bad.json"
    document = {"tool": "amxtriage", "schema_version": 1, "signatures": [{"id": identifier}]}
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(BaselineError, match="invalid"):
        load_baseline(str(path))


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are not available")
def test_symlinked_directories_add_nothing_to_the_index(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leak.pwn").write_text("x\n")
    root = tmp_path / "root"
    root.mkdir()
    try:
        (root / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create symlinks here")
    assert SourceIndex(str(root)).file_count == 0


@pytest.mark.parametrize("filters", [["--top", "1"], ["--min-count", "2"], ["--kind", "crash"]])
def test_saved_baseline_holds_every_problem_whatever_the_display_filters(
    run_cli, sample_log, tmp_path, filters
):
    baseline = tmp_path / "baseline.json"
    result = run_cli("analyze", str(sample_log), *filters, "--save-baseline", str(baseline))
    assert result.returncode == 0
    assert len(load_baseline(str(baseline))) == 5


def test_line_numbers_restart_for_every_input_file(sample_log, tmp_path):
    second = tmp_path / "second.log"
    second.write_text(
        "\n".join(error_block(11, "OnNewCommand", message="Divide by zero")) + "\n",
        encoding="utf-8",
    )
    result = analyze_logs([str(sample_log), str(second)])
    group = next(g for g in result.aggregator.sorted_groups() if g.function == "OnNewCommand")
    assert group.first.line_number == 1


def secret_log(tmp_path, name="server_log.txt"):
    log = tmp_path / name
    lines = [
        '[13:47:10] [debug] Run time error 11: "Divide by zero"',
        "[13:47:10] [debug] AMX backtrace:",
        "[13:47:10] [debug] #0 000b00a4 in public OnDialogResponse"
        f' (playerid=3, inputtext[]=@0000a2f0 "{SECRET}") at gamemodes/rp.pwn:39',
        '[13:47:10] Script[gamemodes/rp.amx]: Run time error 11: "Divide by zero"',
    ]
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log


def watch_output(log, *extra):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    env["PYTHONIOENCODING"] = "utf-8"
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-m",
            "amxtriage",
            "watch",
            str(log),
            "--from-start",
            "--poll-interval",
            "0.1",
            *extra,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    stdout = process.stdout
    collected: list[str] = []

    def pump():
        for raw in iter(stdout.readline, b""):
            collected.append(raw.decode("utf-8", errors="replace"))

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline and "RUNTIME ERROR 11" not in "".join(collected):
            time.sleep(0.05)
        process.send_signal(signal.SIGINT)
        process.wait(timeout=WAIT_SECONDS)
        reader.join(timeout=5)
        return "".join(collected) + process.stderr.read().decode("utf-8", errors="replace")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


@posix_only
def test_watch_mode_hides_arguments_by_default(tmp_path):
    output = watch_output(secret_log(tmp_path))
    assert "RUNTIME ERROR 11" in output
    assert "watch summary" in output
    assert SECRET not in output


@posix_only
def test_watch_mode_shows_arguments_only_with_the_explicit_flag(tmp_path):
    output = watch_output(secret_log(tmp_path), "--show-args")
    assert SECRET in output


@posix_only
@pytest.mark.parametrize("kind", ["binary", "missing", "directory"])
def test_error_messages_never_echo_control_characters_from_file_names(run_cli, tmp_path, kind):
    target = tmp_path / f"evil{HOSTILE}"
    try:
        if kind == "binary":
            target.write_bytes(b"\x00\x01binary\n")
        elif kind == "directory":
            target.mkdir()
    except OSError:
        pytest.skip("this file system rejects control characters in file names")
    result = run_cli("analyze", str(target))
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert result.returncode == 2
    assert "evil" in stderr
    assert dangerous(stderr) == []


@posix_only
def test_saved_baseline_message_never_echoes_control_characters(run_cli, sample_log, tmp_path):
    target = tmp_path / f"base{HOSTILE}.json"
    try:
        target.touch()
    except OSError:
        pytest.skip("this file system rejects control characters in file names")
    target.unlink()
    result = run_cli("analyze", str(sample_log), "--save-baseline", str(target))
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert result.returncode == 0
    assert "saved baseline" in stderr
    assert dangerous(stderr) == []


@posix_only
def test_watch_banner_never_echoes_control_characters_from_the_file_name(tmp_path):
    try:
        log = secret_log(tmp_path, f"evil{HOSTILE}.log")
    except OSError:
        pytest.skip("this file system rejects control characters in file names")
    output = watch_output(log)
    assert "watching evil" in output
    assert dangerous(output) == []
