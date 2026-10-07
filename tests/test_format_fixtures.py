import json
from pathlib import Path
from typing import Any

import pytest

from amxtriage.parser import parse_lines
from amxtriage.reader import LineSplitter
from helpers import project_event

FORMATS = Path(__file__).resolve().parent / "fixtures" / "formats"
MANIFEST: dict[str, Any] = json.loads((FORMATS / "manifest.json").read_text(encoding="utf-8"))
ENTRIES: list[dict[str, Any]] = MANIFEST["fixtures"]
IDS = [entry["file"] for entry in ENTRIES]
STATUSES = {"verified-format", "characterization", "limitation", "unsupported"}
EVIDENCE_TYPES = {"source", "report", "design"}


def parse_bytes(data: bytes, chunk_size: int | None = None) -> list[dict[str, Any]]:
    splitter = LineSplitter()
    lines: list[str] = []
    if chunk_size is None:
        lines.extend(splitter.feed(data))
    else:
        for start in range(0, len(data), chunk_size):
            lines.extend(splitter.feed(data[start : start + chunk_size]))
    lines.extend(splitter.finish())
    return [project_event(event) for event in parse_lines(lines)]


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_fixture_events_match_the_manifest(entry: dict[str, Any]) -> None:
    data = (FORMATS / entry["file"]).read_bytes()
    assert parse_bytes(data) == entry["events"]


@pytest.mark.parametrize("chunk_size", [1, 7, 64])
@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_fixture_events_do_not_depend_on_read_chunking(
    entry: dict[str, Any], chunk_size: int
) -> None:
    data = (FORMATS / entry["file"]).read_bytes()
    assert parse_bytes(data, chunk_size) == entry["events"]


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_fixture_events_do_not_depend_on_line_endings(entry: dict[str, Any]) -> None:
    data = (FORMATS / entry["file"]).read_bytes()
    assert parse_bytes(data.replace(b"\n", b"\r\n")) == entry["events"]


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_fixture_events_survive_a_utf8_byte_order_mark(entry: dict[str, Any]) -> None:
    data = (FORMATS / entry["file"]).read_bytes()
    assert parse_bytes(b"\xef\xbb\xbf" + data) == entry["events"]


def test_every_fixture_file_is_listed_and_every_entry_has_a_file() -> None:
    on_disk = sorted(path.name for path in FORMATS.glob("*.log"))
    assert on_disk == sorted(IDS)
    assert len(set(IDS)) == len(IDS)


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_every_fixture_declares_its_origin_status_and_evidence(entry: dict[str, Any]) -> None:
    assert entry["origin"] == "synthetic"
    assert entry["status"] in STATUSES
    assert entry["summary"].strip()
    assert entry["evidence"]
    for item in entry["evidence"]:
        assert item["type"] in EVIDENCE_TYPES
        assert item["ref"].strip()
        if item["type"] == "report":
            assert item["ref"].startswith("https://")


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_fixture_files_are_portable_plain_text(entry: dict[str, Any]) -> None:
    data = (FORMATS / entry["file"]).read_bytes()
    assert b"\r" not in data
    assert b"\t" not in data
    assert data.isascii()
    assert max(len(line) for line in data.split(b"\n")) < 400


def test_no_event_is_expected_from_the_files_that_describe_non_events() -> None:
    quiet = {
        entry["file"]
        for entry in ENTRIES
        if entry["status"] == "unsupported" or entry["file"] == "false_positives.log"
    }
    assert quiet == {"false_positives.log", "openmp_native_error_lines_unsupported.log"}
    for entry in ENTRIES:
        if entry["file"] in quiet:
            assert entry["events"] == []
