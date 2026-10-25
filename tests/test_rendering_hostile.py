import json
import random
import sys
import unicodedata
from pathlib import Path

import pytest

from amxtriage.analysis import analyze_logs, build_report
from amxtriage.render import render_json, render_markdown, render_text
from amxtriage.source import SourceIndex

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="file names with these characters need a POSIX file system"
)

MARK = "ZQXMARK"
BLOCKED = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})

NAME_FRAGMENTS = [
    "\x1b[31m",
    "\x1b]0;title\x07",
    "\x1b]8;;http://evil.invalid\x07",
    "\x9b31m",
    "\x9d0;x\x9c",
    "\t",
    "\x7f",
    "\x08",
    "\x0b",
    "\x0c",
    "\u202e",
    "\u202d",
    "\u2066",
    "\u200b",
    "\u200e",
    "\ufeff",
    "\u2028",
    "\u2029",
    "\u0085",
    "\U000e0001",
    "\U000f0000",
    "\uffff",
    "`",
    "```",
    "~~~",
    "|",
    "<script>alert(1)</script>",
    "![x](http://evil.invalid/x.png)",
    "[a](javascript:alert(1))",
    "**",
    "# heading",
    "- item",
    ">",
    "&amp;",
    "<!--",
    "-->",
    "$(id)",
    "%s",
    "{0}",
    "\u00e9",
    "\u4e2d",
]
NAME_UNSAFE = ["\n", "\r"]


def hostile(rng: random.Random, *, line_breaks: bool = False) -> str:
    pool = NAME_FRAGMENTS + (NAME_UNSAFE if line_breaks else [])
    parts = [rng.choice(pool) for _ in range(rng.randint(1, 4))]
    return "".join(parts) + MARK + "".join(rng.choice(pool) for _ in range(rng.randint(0, 2)))


def tokens(rng: random.Random) -> str:
    return hostile(rng).replace(" ", "_").replace("(", "<").replace(")", ">").replace('"', "'")


def hostile_log(rng: random.Random, directory: str, source_name: str) -> str:
    lines: list[str] = []
    for index in range(3):
        function = tokens(rng).replace("[", "<").replace("]", ">").replace(":", ";")
        message = hostile(rng).replace('"', "'")
        script = tokens(rng).replace("]", ">").replace("/", "_").replace("\\", "_")
        args = hostile(rng)
        file = f"{directory}/{source_name}" if index == 0 else f"{tokens(rng)}.pwn"
        file = file.replace("\\", "/")
        lines += [
            f'[13:46:0{index}] [debug] Run time error 4: "{message}"',
            f"[13:46:0{index}] [debug] AMX backtrace:",
            f"[13:46:0{index}] [debug] #0 000a1b2c in public {function} ({args}) at {file}:3",
            f"[13:46:0{index}] [debug] #1 0046b2e7 in {tokens(rng)} () in {tokens(rng)}.dll",
            f'[13:46:0{index}] Script[{script}.amx]: Run time error 4: "{message}"',
        ]
    return "\n".join(lines) + "\n"


def assert_clean_characters(output: str) -> None:
    for char in output:
        if char != "\n":
            assert unicodedata.category(char) not in BLOCKED, repr(char)


def assert_markdown_keeps_untrusted_text_in_code(markdown: str) -> None:
    inside_fence = False
    for line in markdown.split("\n"):
        if line.startswith("```"):
            assert line == ("```" if inside_fence else "```text"), repr(line)
            inside_fence = not inside_fence
            continue
        if inside_fence or MARK not in line:
            continue
        segments = line.split("`")
        assert len(segments) % 2 == 1, repr(line)
        for position, segment in enumerate(segments):
            if position % 2 == 0:
                assert MARK not in segment, repr(line)
    assert not inside_fence


def strings_in(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in strings_in(item)] + [
            text for key in value for text in strings_in(key)
        ]
    if isinstance(value, list):
        return [text for item in value for text in strings_in(item)]
    return []


@pytest.mark.parametrize("seed", range(40))
def test_hostile_names_and_text_never_reach_any_output_unsafely(seed: int, tmp_path: Path) -> None:
    rng = random.Random(seed)
    directory = hostile(rng, line_breaks=False).replace("/", "_").replace("\\", "_")
    source_name = hostile(rng, line_breaks=False).replace("/", "_").replace("\\", "_") + ".pwn"
    root = tmp_path / "tree"
    (root / directory).mkdir(parents=True)
    (root / directory / source_name).write_text("".join(f"line {n}\n" for n in range(1, 40)))
    odd_directory = hostile(rng, line_breaks=True).replace("/", "_")
    (root / odd_directory).mkdir()
    (root / odd_directory / (hostile(rng, line_breaks=True).replace("/", "_") + ".pwn")).write_text(
        "x\n"
    )

    log_name = hostile(rng, line_breaks=True).replace("/", "_") + ".log"
    log = tmp_path / log_name
    log.write_text(hostile_log(rng, directory, source_name), encoding="utf-8")

    result = analyze_logs([str(log)])
    index = SourceIndex(str(root))
    report = build_report(result, top=10, source_index=index, context_radius=2)
    assert report.groups
    assert report.contexts

    rendered_text = render_text(report, show_args=True)
    rendered_markdown = render_markdown(report, show_args=True)
    rendered_json = render_json(report, show_args=True)

    assert_clean_characters(rendered_text)
    assert_clean_characters(rendered_markdown)
    assert_markdown_keeps_untrusted_text_in_code(rendered_markdown)
    assert rendered_json.isascii()
    for text in strings_in(json.loads(rendered_json)):
        assert_clean_characters(text)
        assert "\n" not in text

    assert MARK in rendered_text
    assert MARK in rendered_markdown
