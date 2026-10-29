import tracemalloc
from collections.abc import Iterator
from pathlib import Path

import pytest

from amxtriage import parser as parser_module
from amxtriage.aggregate import Aggregator
from amxtriage.analysis import analyze_logs, build_report
from amxtriage.model import ARGS_DISPLAY_LIMIT, MAX_STORED_ARGS
from amxtriage.parser import LogParser, parse_frame
from amxtriage.render import render_json, render_markdown, render_text
from amxtriage.textutil import ELLIPSIS

UNBOUNDED = 10**9
MESSAGE = '"Array index out of bounds"'
LENGTHS = [1, 2, 399, 400, 401, 402, 403, 800, 7000]


def frame_text(args: str) -> str:
    return f"#0 000a1b2c in public OnPlayerUpdate ({args}) at gamemodes/rp.pwn:30"


def log_with_arguments(args: str) -> str:
    return (
        "\n".join(
            [
                '[13:46:01] [debug] Run time error 4: "Array index out of bounds"',
                "[13:46:01] [debug] AMX backtrace:",
                f"[13:46:01] [debug] #0 000a1b2c in public OnPlayerUpdate ({args}) at rp.pwn:30",
                f"[13:46:01] [debug] #1 000a1b2d in Helper ({args}) at rp.pwn:12",
                f"[13:46:01] Script[gamemodes/rp.amx]: Run time error 4: {MESSAGE}",
            ]
        )
        + "\n"
    )


def hostile_lines(groups: int, frames: int = 48, size: int = 8000) -> Iterator[str]:
    filler = "A" * size
    for group in range(groups):
        yield '[13:46:01] [debug] Run time error 4: "Array index out of bounds"'
        yield "[13:46:01] [debug] AMX backtrace:"
        for index in range(frames):
            name = f"Fn{group:05d}" if index == 0 else "Inner"
            keyword = "public " if index == 0 else ""
            yield (
                f'[13:46:01] [debug] #{index} 000a1b2c in {keyword}{name} (a="{filler}") '
                f"at rp.pwn:{30 + index}"
            )
        yield '[13:46:01] Script[gamemodes/rp.amx]: Run time error 4: "Array index out of bounds"'


def retained_bytes(groups: int, size: int = 8000) -> int:
    parser = LogParser()
    aggregator = Aggregator()
    tracemalloc.start()
    try:
        for line in hostile_lines(groups, size=size):
            for event in parser.feed(line):
                aggregator.add(event, "input")
        for event in parser.flush():
            aggregator.add(event, "input")
        current, _peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(aggregator) == groups
    return current


def rendered(path: Path, *, show_args: bool) -> tuple[str, str, str, list[tuple[str, int]]]:
    result = analyze_logs([str(path)])
    report = build_report(result, top=5)
    groups = [(group.signature_id, group.count) for group in report.groups]
    return (
        render_text(report, show_args=show_args),
        render_markdown(report, show_args=show_args),
        render_json(report, show_args=show_args),
        groups,
    )


def test_the_limits_are_four_hundred_for_display_and_one_more_for_storage() -> None:
    assert ARGS_DISPLAY_LIMIT == 400
    assert MAX_STORED_ARGS == 401


@pytest.mark.parametrize("length", LENGTHS)
def test_arguments_are_cut_when_the_frame_is_parsed(length: int) -> None:
    frame = parse_frame(frame_text("A" * length))
    assert frame is not None
    assert frame.args == "A" * min(length, MAX_STORED_ARGS)


def test_the_cut_counts_characters_not_bytes() -> None:
    frame = parse_frame(frame_text("\u00e9" * 1000))
    assert frame is not None
    assert frame.args == "\u00e9" * MAX_STORED_ARGS


def test_empty_arguments_stay_empty() -> None:
    frame = parse_frame(frame_text(""))
    assert frame is not None
    assert frame.args == ""


def test_the_rest_of_the_frame_is_not_affected_by_the_cut() -> None:
    frame = parse_frame(frame_text("A" * 5000))
    assert frame is not None
    assert (frame.function, frame.public, frame.file, frame.line) == (
        "OnPlayerUpdate",
        True,
        "gamemodes/rp.pwn",
        30,
    )


@pytest.mark.parametrize("show_args", [False, True])
@pytest.mark.parametrize("length", LENGTHS)
def test_output_is_identical_to_storing_every_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, length: int, show_args: bool
) -> None:
    path = tmp_path / "server_log.txt"
    path.write_text(
        log_with_arguments("Ab\tc\u202e" * (length // 5) + "Z" * (length % 5)),
        encoding="utf-8",
    )
    current = rendered(path, show_args=show_args)
    monkeypatch.setattr(parser_module, "MAX_STORED_ARGS", UNBOUNDED)
    reference = rendered(path, show_args=show_args)
    assert current == reference


def test_long_arguments_are_shown_cut_with_an_ellipsis_only_when_requested(tmp_path: Path) -> None:
    path = tmp_path / "server_log.txt"
    path.write_text(log_with_arguments("A" * 5000), encoding="utf-8")
    hidden_text, hidden_markdown, hidden_json, _ = rendered(path, show_args=False)
    assert "AAAA" not in hidden_text + hidden_markdown + hidden_json
    shown_text, shown_markdown, shown_json, _ = rendered(path, show_args=True)
    expected = "A" * (ARGS_DISPLAY_LIMIT - len(ELLIPSIS)) + ELLIPSIS
    assert len(expected) == ARGS_DISPLAY_LIMIT
    assert f"({expected})" in shown_text
    assert f"({expected})" in shown_markdown
    assert f'"args": "{expected}"' in shown_json


def test_a_hostile_log_keeps_the_retained_memory_small() -> None:
    assert retained_bytes(40) < 6 * 1024 * 1024


def test_the_retained_memory_does_not_depend_on_the_length_of_long_arguments() -> None:
    long = retained_bytes(10, size=1000)
    longer = retained_bytes(10, size=8000)
    assert long > 0
    assert longer < long * 1.2
