from collections.abc import Callable, Iterator
from typing import Any

import pytest

from amxtriage import cli

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
