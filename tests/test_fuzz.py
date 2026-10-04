import json
import random
from pathlib import Path

import pytest

from amxtriage.analysis import analyze_logs, build_report
from amxtriage.parser import MAX_FRAMES, LogParser, parse_lines
from amxtriage.reader import LineSplitter
from amxtriage.render import render_json, render_markdown, render_text

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample_server_log.txt"
KINDS = {"runtime_error", "crash", "long_call", "interrupt"}
FRAGMENTS = [
    "[",
    "]",
    "#",
    ":",
    "(",
    ")",
    " ",
    '"',
    "\x1b",
    "\u202e",
    "\x00",
    "\u00e9",
    "native ",
    "public ",
    " at ",
    " in ",
    " from ",
    "Run time error ",
    "Script[",
    "AMX backtrace:",
    "Native backtrace:",
    "Server crashed while executing ",
    "0",
    "9",
    "a",
    "-",
    "<",
    ">",
    "=",
    "@",
    "&",
]


def mutate(line, rng):
    choice = rng.randrange(6)
    if choice == 0 and line:
        return line[: rng.randrange(len(line))]
    if choice == 1:
        position = rng.randrange(len(line) + 1)
        return line[:position] + rng.choice(FRAGMENTS) + line[position:]
    if choice == 2 and line:
        position = rng.randrange(len(line))
        return line[:position] + line[position + 1 :]
    if choice == 3:
        return line + rng.choice(FRAGMENTS) * rng.randrange(1, 50)
    if choice == 4:
        return rng.choice(FRAGMENTS) + line
    return line


def mutated_lines(rng):
    base = SAMPLE.read_text(encoding="utf-8").splitlines()
    lines = [mutate(line, rng) if rng.random() < 0.4 else line for line in base]
    if rng.random() < 0.3:
        rng.shuffle(lines)
    if rng.random() < 0.3:
        lines = lines[: rng.randrange(len(lines))]
    return lines


def chunked(data, rng, largest):
    position = 0
    while position < len(data):
        size = rng.randrange(1, largest + 1)
        yield data[position : position + size]
        position += size


@pytest.mark.parametrize("seed", range(150))
def test_mutated_logs_never_crash_the_parser_and_keep_event_invariants(seed):
    rng = random.Random(seed)
    for event in parse_lines(mutated_lines(rng)):
        assert event.kind in KINDS
        assert event.line_number >= 1
        assert len(event.frames) <= MAX_FRAMES
        assert all(isinstance(frame.index, int) for frame in event.frames)
        assert event.code is None or 0 <= event.code <= 999


@pytest.mark.parametrize("seed", range(60))
def test_random_bytes_never_crash_splitter_or_parser(seed):
    rng = random.Random(1000 + seed)
    data = rng.randbytes(rng.randrange(0, 40000))
    splitter = LineSplitter(max_line_bytes=200)
    parser = LogParser()
    lines = []
    for chunk in chunked(data, rng, 3000):
        lines.extend(splitter.feed(chunk))
    lines.extend(splitter.finish())
    for line in lines:
        parser.feed(line)
    parser.flush()
    expected = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
    assert len(lines) == expected
    assert splitter.lines == expected


@pytest.mark.parametrize("seed", range(60))
def test_chunking_never_changes_the_resulting_lines(seed):
    rng = random.Random(5000 + seed)
    alphabet = b"abc\n\r \xef\xbb\xbf\xff[]"
    data = bytes(rng.choice(alphabet) for _ in range(rng.randrange(0, 4000)))
    whole = LineSplitter(max_line_bytes=40)
    expected = whole.feed(data) + whole.finish()
    pieces = LineSplitter(max_line_bytes=40)
    actual = []
    for chunk in chunked(data, rng, 97):
        actual.extend(pieces.feed(chunk))
    actual.extend(pieces.finish())
    assert actual == expected
    assert pieces.truncated == whole.truncated


def test_splitting_the_sample_log_at_every_offset_gives_identical_lines():
    data = SAMPLE.read_bytes()
    whole = LineSplitter()
    expected = whole.feed(data) + whole.finish()
    for offset in range(0, len(data) + 1, 7):
        splitter = LineSplitter()
        lines = splitter.feed(data[:offset]) + splitter.feed(data[offset:]) + splitter.finish()
        assert lines == expected, offset


@pytest.mark.parametrize("seed", range(40))
def test_mutated_logs_flow_through_the_whole_pipeline_in_every_format(seed, tmp_path):
    rng = random.Random(9000 + seed)
    path = tmp_path / "fuzz.log"
    text = "\n".join(mutated_lines(rng)).replace("\x00", "") + "\n"
    path.write_text(text, encoding="utf-8", errors="replace")
    report = build_report(analyze_logs([str(path)]), top=50)
    for show_args in (False, True):
        for output in (
            render_text(report, show_args=show_args),
            render_markdown(report, show_args=show_args),
        ):
            assert all(char == "\n" or ord(char) >= 0x20 for char in output)
            assert "\x7f" not in output
        json.loads(render_json(report, show_args=show_args))
