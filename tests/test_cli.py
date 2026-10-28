import io
import json
import sys

import pytest

from amxtriage import cli
from amxtriage.cli import expand_paths, main
from amxtriage.errors import InputError
from helpers import error_block


def run(argv, capsys):
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def write_log(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def test_analyze_prints_a_text_report(sample_log, capsys):
    code, out, err = run(["analyze", str(sample_log)], capsys)
    assert code == 0
    assert "RUNTIME ERROR 4: Array index out of bounds" in out
    assert err == ""


def test_analyze_supports_markdown_and_json_formats(sample_log, capsys):
    _, markdown, _ = run(["analyze", str(sample_log), "--format", "markdown"], capsys)
    assert markdown.startswith("# amxtriage report")
    _, raw, _ = run(["analyze", str(sample_log), "--format", "json"], capsys)
    assert json.loads(raw)["summary"]["events"] == 7


def test_output_option_writes_utf8_file_and_prints_nothing(tmp_path, capsys):
    log = write_log(
        tmp_path / "log.txt",
        [
            '[13:46:01] [debug] Run time error 4: "Array index out of bounds"',
            "[13:46:01] [debug] AMX backtrace:",
            "[13:46:01] [debug] #0 000a1b2c in public Caf\u00e9 ()"
            " at gamemodes/r\u00e9sum\u00e9.pwn:3",
        ],
    )
    target = tmp_path / "report.md"
    code, out, _ = run(["analyze", log, "--format", "markdown", "-o", str(target)], capsys)
    assert code == 0
    assert out == ""
    assert "Caf\u00e9" in target.read_bytes().decode("utf-8")


def test_output_to_an_unwritable_location_is_a_clean_error(sample_log, tmp_path, capsys):
    code, _, err = run(["analyze", str(sample_log), "-o", str(tmp_path)], capsys)
    assert code == 2
    assert "error: cannot write" in err


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["analyze", "x.log", "--top", "0"], "must be at least 1"),
        (["analyze", "x.log", "--top", "abc"], "invalid integer"),
        (["analyze", "x.log", "--min-count", "-3"], "must be at least 1"),
        (["analyze", "x.log", "--context", "99"], "between 0 and 20"),
        (["analyze", "x.log", "--format", "yaml"], "invalid choice"),
        (["analyze", "x.log", "--kind", "bogus"], "invalid choice"),
        (["watch", "x.log", "--poll-interval", "0"], "must be between"),
        (["watch", "x.log", "--poll-interval", "soon"], "invalid number"),
        (["watch", "x.log", "--alert-cooldown", "nan"], "between 0 and 86400"),
        (["watch", "x.log", "--alert-max-per-minute", "0"], "must be between 1 and 300"),
        (["explain", "-4"], "must be at least 0"),
        (["analyze"], "required"),
        ([], "required"),
    ],
)
def test_invalid_arguments_exit_with_status_two(argv, message, capsys):
    with pytest.raises(SystemExit) as raised:
        main(argv)
    assert raised.value.code == 2
    assert message in capsys.readouterr().err


def test_fail_on_new_requires_a_baseline(sample_log, capsys):
    with pytest.raises(SystemExit) as raised:
        main(["analyze", str(sample_log), "--fail-on-new"])
    assert raised.value.code == 2
    assert "--fail-on-new requires --baseline" in capsys.readouterr().err


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as raised:
        main(["--version"])
    assert raised.value.code == 0
    assert capsys.readouterr().out.startswith("amxtriage ")


def test_missing_log_is_a_clean_error_without_traceback(tmp_path, capsys):
    code, out, err = run(["analyze", str(tmp_path / "nope.log")], capsys)
    assert code == 2
    assert out == ""
    assert err.startswith("error: cannot open")
    assert "Traceback" not in err


def test_binary_input_is_a_clean_error(tmp_path, capsys):
    binary = tmp_path / "gamemode.amx"
    binary.write_bytes(b"\x00\x01\x02\x03")
    code, _, err = run(["analyze", str(binary)], capsys)
    assert code == 2
    assert "binary" in err


def test_baseline_workflow_detects_only_new_problems(sample_log, tmp_path, capsys):
    baseline = str(tmp_path / "baseline.json")
    code, _, err = run(["analyze", str(sample_log), "--save-baseline", baseline], capsys)
    assert code == 0
    assert "saved baseline with 5 signature(s)" in err

    code, out, _ = run(
        ["analyze", str(sample_log), "--baseline", baseline, "--fail-on-new"], capsys
    )
    assert code == 0
    assert "0 new problems (5 known problem(s) hidden by baseline)" in out

    fresh = write_log(
        tmp_path / "next.log",
        [
            *error_block(4, "OnPlayerUpdate"),
            *error_block(11, "OnNewCommand", message="Divide by zero"),
        ],
    )
    code, out, _ = run(["analyze", fresh, "--baseline", baseline, "--fail-on-new"], capsys)
    assert code == 1
    assert "NEW  RUNTIME ERROR 11: Divide by zero" in out
    assert "OnPlayerUpdate" not in out


def test_new_problems_do_not_fail_the_run_without_fail_on_new(sample_log, tmp_path, capsys):
    baseline = str(tmp_path / "baseline.json")
    save_code, _, _ = run(["analyze", str(sample_log), "--save-baseline", baseline], capsys)
    fresh = write_log(
        tmp_path / "next.log", error_block(11, "OnNewCommand", message="Divide by zero")
    )
    code, out, _ = run(["analyze", fresh, "--baseline", baseline], capsys)
    assert (save_code, code) == (0, 0)
    assert "1 new problem " in out


def test_baseline_can_be_compared_and_refreshed_in_one_run(sample_log, tmp_path, capsys):
    baseline = str(tmp_path / "baseline.json")
    run(["analyze", str(sample_log), "--save-baseline", baseline], capsys)
    fresh = write_log(
        tmp_path / "next.log", error_block(11, "OnNewCommand", message="Divide by zero")
    )
    run(["analyze", fresh, "--baseline", baseline, "--save-baseline", baseline], capsys)
    code, out, _ = run(["analyze", fresh, "--baseline", baseline, "--fail-on-new"], capsys)
    assert code == 0
    assert "0 new problems" in out


def test_invalid_baseline_is_a_clean_error(sample_log, tmp_path, capsys):
    broken = tmp_path / "baseline.json"
    broken.write_text("{nope")
    code, _, err = run(["analyze", str(sample_log), "--baseline", str(broken)], capsys)
    assert code == 2
    assert "cannot read baseline" in err


def test_saving_a_baseline_to_a_missing_directory_is_a_clean_error(sample_log, tmp_path, capsys):
    target = str(tmp_path / "missing" / "baseline.json")
    code, _, err = run(["analyze", str(sample_log), "--save-baseline", target], capsys)
    assert code == 2
    assert "cannot write baseline" in err


def test_kind_and_min_count_filters(sample_log, capsys):
    _, out, _ = run(["analyze", str(sample_log), "--kind", "crash", "--kind", "crash"], capsys)
    assert "CRASH" in out
    assert "RUNTIME ERROR" not in out
    _, out, _ = run(["analyze", str(sample_log), "--min-count", "2"], capsys)
    assert "RUNTIME ERROR 4" in out
    assert "CRASH" not in out


def test_top_limits_the_listing(sample_log, capsys):
    _, out, _ = run(["analyze", str(sample_log), "--top", "1"], capsys)
    assert "[1]" in out
    assert "[2]" not in out
    assert "4 more problem(s) not shown" in out


def test_source_dir_adds_context_and_context_zero_removes_it(sample_log, sample_sources, capsys):
    base = ["analyze", str(sample_log), "--source-dir", str(sample_sources)]
    _, out, _ = run(base, capsys)
    assert "> 39 |     new average = total / count;" in out
    _, out, _ = run([*base, "--context", "0"], capsys)
    assert "source :" not in out


def test_invalid_source_dir_is_a_clean_error(sample_log, tmp_path, capsys):
    code, _, err = run(["analyze", str(sample_log), "--source-dir", str(tmp_path / "nope")], capsys)
    assert code == 2
    assert "source directory" in err


def test_show_args_flag_reveals_arguments(sample_log, capsys):
    _, hidden, _ = run(["analyze", str(sample_log)], capsys)
    _, shown, _ = run(["analyze", str(sample_log), "--show-args"], capsys)
    assert "hunter2-secret" not in hidden
    assert "hunter2-secret" in shown


def test_wildcards_are_expanded_for_shells_that_do_not_glob(tmp_path, capsys):
    write_log(tmp_path / "a.log", error_block(4, "A"))
    write_log(tmp_path / "b.log", error_block(4, "B"))
    code, out, _ = run(["analyze", str(tmp_path / "*.log")], capsys)
    assert code == 0
    assert "input  : a.log, b.log" in out


def test_wildcard_without_matches_is_an_error(tmp_path, capsys):
    code, _, err = run(["analyze", str(tmp_path / "*.log")], capsys)
    assert code == 2
    assert "no files match" in err


def test_expand_paths_keeps_existing_files_with_wildcard_characters(tmp_path):
    odd = tmp_path / "log[1].txt"
    odd.write_text("x")
    assert expand_paths([str(odd), "-"]) == [str(odd), "-"]


def test_expand_paths_sorts_matches_alphabetically(tmp_path):
    for name in ("c.log", "a.log", "b.log"):
        (tmp_path / name).write_text("x")
    names = [path.rsplit("/", 1)[-1] for path in expand_paths([str(tmp_path / "*.log")])]
    assert names == ["a.log", "b.log", "c.log"]


def test_expand_paths_raises_input_error_without_matches(tmp_path):
    with pytest.raises(InputError):
        expand_paths([str(tmp_path / "*.nothing")])


def test_stdin_is_analyzed_when_dash_is_given(sample_log, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(sample_log.read_bytes())))
    code, out, _ = run(["analyze", "-"], capsys)
    assert code == 0
    assert "input  : <stdin>" in out
    assert "5 distinct problems" in out


def test_language_option_is_available_before_and_after_subcommand(sample_log, capsys):
    code, out, _ = run(["--language", "id", "analyze", str(sample_log)], capsys)
    assert code == 0
    assert "masukan:" in out
    code, out, _ = run(["analyze", str(sample_log), "--lang", "es"], capsys)
    assert code == 0
    assert "entrada:" in out


def test_explain_known_code(capsys):
    code, out, _ = run(["explain", "4"], capsys)
    assert code == 0
    assert "AMX error 4: Array index out of bounds" in out


def test_explain_without_code_lists_all_codes(capsys):
    code, out, _ = run(["explain"], capsys)
    assert code == 0
    assert "19  File or function is not found" in out


def test_explain_unknown_code_is_an_error(capsys):
    code, _, err = run(["explain", "999"], capsys)
    assert code == 2
    assert "unknown AMX error code 999" in err


def test_closed_pipe_ends_quietly_with_success(sample_log, monkeypatch, capsys):
    def broken_pipe(*_args, **_kwargs):
        raise BrokenPipeError

    monkeypatch.setattr(cli, "_write_output", broken_pipe)
    monkeypatch.setattr(cli, "_silence_stdout", lambda: None)
    code, _, _ = run(["analyze", str(sample_log)], capsys)
    assert code == 0


def test_keyboard_interrupt_returns_conventional_status(sample_log, monkeypatch, capsys):
    def interrupted(_args):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_run_analyze", interrupted)
    code, _, _ = run(["analyze", str(sample_log)], capsys)
    assert code == 130


def test_subprocess_run_produces_report_and_zero_exit(run_cli, sample_log):
    result = run_cli("analyze", str(sample_log))
    assert result.returncode == 0
    assert b"RUNTIME ERROR 4" in result.stdout
    assert result.stderr == b""


def test_subprocess_missing_file_prints_clean_error(run_cli, tmp_path):
    result = run_cli("analyze", str(tmp_path / "nope.log"))
    assert result.returncode == 2
    assert result.stderr.startswith(b"error: cannot open")
    assert b"Traceback" not in result.stderr


def test_subprocess_reads_stdin_pipe(run_cli, sample_log):
    result = run_cli("analyze", "-", "--format", "json", input_bytes=sample_log.read_bytes())
    assert result.returncode == 0
    assert json.loads(result.stdout)["summary"]["sources"] == ["<stdin>"]


def test_subprocess_output_is_utf8(run_cli, tmp_path):
    log = write_log(
        tmp_path / "log.txt",
        [
            '[13:46:01] [debug] Run time error 4: "Array index out of bounds"',
            "[13:46:01] [debug] AMX backtrace:",
            "[13:46:01] [debug] #0 000a1b2c in public Caf\u00e9 () at gamemodes/r.pwn:3",
        ],
    )
    result = run_cli("analyze", log)
    assert "Caf\u00e9" in result.stdout.decode("utf-8")


def test_patch_preview_cli_emits_unified_diff_without_editing_source(tmp_path, capsys):
    root = tmp_path / "source"
    source = root / "gamemodes" / "rp.pwn"
    source.parent.mkdir(parents=True)
    source.write_text("new value = 42\nreturn 1;\n", encoding="utf-8")
    before = source.read_bytes()
    compiler_log = write_log(
        tmp_path / "compiler.log",
        ['gamemodes/rp.pwn(2) : error 001: expected token: ";", but found "return"'],
    )

    code, out, err = run(
        [
            "patch-preview",
            compiler_log,
            "--source-dir",
            str(root),
            "--format",
            "unified",
        ],
        capsys,
    )

    assert code == 0
    assert err == ""
    assert out.startswith("--- a/gamemodes/rp.pwn\n")
    assert "+new value = 42;\n" in out
    assert source.read_bytes() == before


def test_patch_preview_cli_returns_three_when_no_safe_patch_exists(tmp_path, capsys):
    root = tmp_path / "source"
    root.mkdir()
    source = root / "rp.pwn"
    source.write_text("new value = 42\nreturn 1;\n", encoding="utf-8")
    compiler_log = write_log(
        tmp_path / "compiler.log",
        ['rp.pwn(2) : error 017: undefined symbol "PlayerData"'],
    )

    code, out, err = run(
        ["patch-preview", compiler_log, "--source-dir", str(root), "--format", "unified"],
        capsys,
    )

    assert code == cli.EXIT_NO_PATCH
    assert out == ""
    assert "No supported high-confidence fix candidate" in err
    assert source.read_text(encoding="utf-8") == "new value = 42\nreturn 1;\n"


def test_patch_preview_unified_rejects_multiple_expanded_logs(tmp_path, capsys):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    write_log(logs_dir / "first.log", ["first log"])
    write_log(logs_dir / "second.log", ["second log"])
    source_root = tmp_path / "source"
    source_root.mkdir()

    code, out, err = run(
        [
            "patch-preview",
            str(logs_dir / "*.log"),
            "--source-dir",
            str(source_root),
            "--format",
            "unified",
        ],
        capsys,
    )

    assert code == cli.EXIT_ERROR
    assert out == ""
    assert "accepts one compiler log at a time" in err


def test_subprocess_module_help_works(run_cli):
    result = run_cli("--help")
    assert result.returncode == 0
    assert b"analyze" in result.stdout
    assert b"watch" in result.stdout
    assert b"explain" in result.stdout
