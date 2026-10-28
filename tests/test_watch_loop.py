import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from amxtriage import cli
from amxtriage.monitoring import metrics_supported

BLOCK = [
    '[13:46:01] [debug] Run time error 4: "Array index out of bounds"',
    "[13:46:01] [debug] AMX backtrace:",
    "[13:46:01] [debug] #0 000a1b2c in public OnPlayerUpdate (playerid=0) at gamemodes/rp.pwn:30",
]
SCRIPT = '[13:46:01] Script[gamemodes/rp.amx]: Run time error 4: "Array index out of bounds"'


class ScriptedFollower:
    def __init__(self, items: list[Any]) -> None:
        self._items = items
        self.truncated_lines = 0
        self.closed = False

    def lines(self) -> Iterator[str | None]:
        for item in self._items:
            if callable(item):
                item()
            else:
                yield item

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def run_watch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Callable[..., Any]:
    def run(items: list[Any], *extra: str) -> tuple[int, str, str]:
        follower = ScriptedFollower(items)
        monkeypatch.setattr(cli, "LogFollower", lambda *args, **kwargs: follower)
        code = cli.main(["watch", "server_log.txt", *extra])
        captured = capsys.readouterr()
        assert follower.closed
        return code, captured.out, captured.err

    return run


RunWatch = Callable[..., tuple[int, str, str]]


def test_a_script_line_that_arrives_one_poll_later_joins_its_block(run_watch: RunWatch) -> None:
    code, out, _ = run_watch([*BLOCK, None, SCRIPT, None, None, None])
    assert code == 0
    assert out.count("NEW  RUNTIME ERROR 4") == 1
    assert "x1" in out
    assert "rp.amx" in out


def test_a_block_is_reported_once_the_log_has_been_quiet_for_a_while(
    run_watch: RunWatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []
    items = [*BLOCK, None, None, lambda: seen.append(capsys.readouterr().out), "[13:46:09] later"]
    run_watch(items)
    assert len(seen) == 1
    assert seen[0].count("NEW  RUNTIME ERROR 4") == 1


def test_a_block_is_still_pending_after_a_single_quiet_poll(
    run_watch: RunWatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []
    items = [*BLOCK, None, lambda: seen.append(capsys.readouterr().out), "[13:46:09] later"]
    run_watch(items)
    assert seen == [""]


def test_new_lines_restart_the_wait_for_a_pending_block(
    run_watch: RunWatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []
    items = [
        *BLOCK,
        None,
        "[13:46:02] unrelated one",
        None,
        lambda: seen.append(capsys.readouterr().out),
        None,
        lambda: seen.append(capsys.readouterr().out),
    ]
    run_watch(items)
    assert seen[0] == ""
    assert seen[1].count("NEW  RUNTIME ERROR 4") == 1


def test_the_final_summary_includes_a_block_that_was_still_pending(run_watch: RunWatch) -> None:
    _, out, _ = run_watch([*BLOCK])
    assert out.count("NEW  RUNTIME ERROR 4") == 1
    assert "watch summary" in out


def test_watch_exports_structured_jsonl_alert_with_protected_location(
    run_watch: RunWatch, tmp_path: Path
) -> None:
    target = tmp_path / "alerts.jsonl"
    code, out, err = run_watch(
        [*BLOCK, None, None],
        "--alert-jsonl",
        str(target),
        "--alert-prefix",
        "OWNER",
        "--alert-template",
        "{prefix} {severity}: {message}",
    )
    assert code == 0
    assert "warning: local alert export disabled" not in err
    assert "NEW  RUNTIME ERROR 4" in out
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["summary"] == "OWNER HIGH: Array index out of bounds"
    assert event["source"] == {"file": "gamemodes/rp.pwn", "line": 30}
    assert event["presentation"] == {"file_color": "red", "line_color": "blue"}


def test_alert_export_failure_does_not_stop_log_following(
    run_watch: RunWatch, tmp_path: Path
) -> None:
    code, out, err = run_watch([*BLOCK, None, None], "--alert-jsonl", str(tmp_path))
    assert code == 0
    assert "warning: local alert export disabled" in err
    assert "NEW  RUNTIME ERROR 4" in out
    assert "watch summary" in out


def test_watch_exports_pawn_bridge_record_for_filterscript(
    run_watch: RunWatch, tmp_path: Path
) -> None:
    target = tmp_path / "amxtriage-alerts.txt"
    code, out, err = run_watch(
        [*BLOCK, None, None],
        "--alert-pawn-file",
        str(target),
        "--alert-prefix",
        "SERVER",
    )
    assert code == 0
    assert "local alert export disabled" not in err
    assert "NEW  RUNTIME ERROR 4" in out
    records = target.read_text(encoding="utf-8").splitlines()
    assert len(records) == 1
    fields = records[0].split("|")
    assert len(fields) == 8
    assert fields[0] == "AMXTRIAGE1"
    assert fields[1] == "HIGH"
    assert fields[2] == "SERVER"
    assert fields[3] == "gamemodes/rp.pwn"
    assert fields[4] == "30"
    assert fields[5] == "Array index out of bounds"
    assert fields[7] == "END"


def test_watch_writes_opt_in_metrics_jsonl_and_processing_latency(
    run_watch: RunWatch, tmp_path: Path
) -> None:
    target = tmp_path / "metrics.jsonl"
    code, _out, err = run_watch(
        [*BLOCK, None, None],
        "--alert-jsonl",
        str(tmp_path / "alerts.jsonl"),
        "--metrics-jsonl",
        str(target),
        "--metrics-interval",
        "1",
    )
    assert code == 0
    assert "metrics export disabled" not in err
    records = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    assert records
    assert all(record["event_type"] == "metrics.sample" for record in records)
    assert "cpu_percent" in records[0]["system"]
    assert "memory_used_percent" in records[0]["system"]
    assert "rss_bytes" in records[0]["process"]
    assert "read_bytes_per_second" in records[0]["disk_io"]
    assert records[-1]["alert_processing"]["count"] >= 1


def test_metrics_output_must_not_overwrite_the_log(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    if not metrics_supported():
        pytest.skip("Linux host metrics are not supported on this runner")
    log = tmp_path / "server_log.txt"
    log.write_text("", encoding="utf-8")

    def unexpected_follower(*args: object, **kwargs: object) -> None:
        pytest.fail("metrics path conflicts must fail before watching")

    monkeypatch.setattr(cli, "LogFollower", unexpected_follower)
    assert cli.main(["watch", str(log), "--metrics-jsonl", str(log)]) == cli.EXIT_ERROR
    assert "metrics output must be a separate file" in capsys.readouterr().err


def test_alert_template_requires_jsonl_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unexpected_follower(*args: object, **kwargs: object) -> None:
        pytest.fail("invalid configuration must fail before watching")

    monkeypatch.setattr(cli, "LogFollower", unexpected_follower)
    with pytest.raises(SystemExit) as raised:
        cli.main(["watch", "server_log.txt", "--alert-template", "{prefix}: {message}"])
    captured = capsys.readouterr()
    assert raised.value.code == 2
    assert captured.out == ""
    assert "--alert-template requires --alert-jsonl" in captured.err
