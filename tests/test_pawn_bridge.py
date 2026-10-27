from __future__ import annotations

import os
from pathlib import Path

import pytest

from amxtriage.aggregate import Aggregator
from amxtriage.alerts import (
    PawnBridgeAlertSink,
    append_pawn_bridge_record,
    serialize_pawn_bridge_record,
)
from amxtriage.errors import InputError, OutputError
from amxtriage.model import Event, EventKind, Frame, Group


def make_group(
    *,
    kind: EventKind = "runtime_error",
    message: str = "Array index out of bounds",
    file: str = "gamemodes/rp.pwn",
    line: int = 42,
) -> Group:
    event = Event(
        kind=kind,
        line_number=8,
        timestamp="13:46:01",
        code=4 if kind == "runtime_error" else None,
        message=message,
        script="gamemodes/rp.amx",
        details=(),
        frames=(
            Frame(
                index=0,
                kind="amx",
                function="OnPlayerUpdate",
                public=True,
                file=file,
                line=line,
                module=None,
                args=None,
            ),
        ),
        native_frames=(),
    )
    group = Aggregator().add(event, "server_log.txt").group
    assert group is not None
    return group


def test_pawn_bridge_record_has_stable_fields_and_protected_location() -> None:
    record = serialize_pawn_bridge_record(make_group(), prefix="SERVER WATCH")
    assert record.endswith("\n")
    fields = record.rstrip("\n").split("|")
    assert len(fields) == 8
    assert fields[0] == "AMXTRIAGE1"
    assert fields[1] == "HIGH"
    assert fields[2] == "SERVER WATCH"
    assert fields[3] == "gamemodes/rp.pwn"
    assert fields[4] == "42"
    assert fields[5] == "Array index out of bounds"
    assert fields[6] == "1"
    assert fields[7] == "END"


def test_pawn_bridge_escapes_record_delimiters_and_color_tag_braces() -> None:
    record = serialize_pawn_bridge_record(
        make_group(message="100% ready | {FF0000}red\nsecond line", file="r|p{FF0000}.pwn")
    )
    fields = record.rstrip("\n").split("|")
    assert len(fields) == 8
    assert fields[3] == "r%7Cp%7BFF0000%7D.pwn"
    assert fields[5] == "100%25 ready %7C %7BFF0000%7Dred?second line"


@pytest.mark.parametrize("prefix", ["line\nadmin", "bad\tadmin", "x" * 81])
def test_pawn_bridge_rejects_unsafe_prefix(prefix: str) -> None:
    with pytest.raises(InputError, match="alert prefix"):
        serialize_pawn_bridge_record(make_group(), prefix=prefix)


@pytest.mark.parametrize(
    ("kind", "severity"),
    [
        ("crash", "CRITICAL"),
        ("runtime_error", "HIGH"),
        ("long_call", "MEDIUM"),
    ],
)
def test_pawn_bridge_maps_severity(kind: EventKind, severity: str) -> None:
    fields = serialize_pawn_bridge_record(make_group(kind=kind)).rstrip("\n").split("|")
    assert fields[1] == severity


def test_pawn_bridge_uses_zero_when_source_line_is_missing() -> None:
    fields = serialize_pawn_bridge_record(make_group(line=0)).rstrip("\n").split("|")
    assert fields[4] == "0"


def test_pawn_bridge_appends_records_to_private_file(tmp_path: Path) -> None:
    target = tmp_path / "amxtriage-alerts.txt"
    append_pawn_bridge_record(str(target), make_group())
    append_pawn_bridge_record(str(target), make_group(kind="crash"))
    records = target.read_text(encoding="utf-8").splitlines()
    assert len(records) == 2
    assert records[0].startswith("AMXTRIAGE1|HIGH|")
    assert records[1].startswith("AMXTRIAGE1|CRITICAL|")
    if os.name == "posix":
        assert target.stat().st_mode & 0o777 == 0o600


def test_pawn_bridge_sink_disables_after_output_failure(tmp_path: Path) -> None:
    sink = PawnBridgeAlertSink(str(tmp_path))
    assert sink.emit(make_group()) is False
    assert sink.disabled is True
    assert sink.failure_reason is not None
    assert sink.emit(make_group()) is False


def test_pawn_bridge_refuses_symlinks_without_modifying_target(tmp_path: Path) -> None:
    target = tmp_path / "real.txt"
    target.write_text("keep\n", encoding="utf-8")
    link = tmp_path / "bridge.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable on this runner")
    with pytest.raises(OutputError, match="symbolic link"):
        append_pawn_bridge_record(str(link), make_group())
    assert target.read_text(encoding="utf-8") == "keep\n"


def test_pawn_bridge_refuses_hard_links_without_modifying_target(tmp_path: Path) -> None:
    target = tmp_path / "real.txt"
    target.write_text("keep\n", encoding="utf-8")
    link = tmp_path / "other.txt"
    try:
        os.link(target, link)
    except OSError:
        pytest.skip("hard links are unavailable on this runner")
    with pytest.raises(OutputError, match="hard links"):
        append_pawn_bridge_record(str(target), make_group())
    assert target.read_text(encoding="utf-8") == "keep\n"
