import json
import os
from pathlib import Path

import pytest

from amxtriage.alerts import (
    DEFAULT_ALERT_TEMPLATE,
    JsonlAlertSink,
    append_alert_event,
    build_alert_event,
    serialize_alert_event,
)
from amxtriage.aggregate import Aggregator
from amxtriage.errors import InputError
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


def test_alert_event_keeps_structured_location_and_color_metadata() -> None:
    event = build_alert_event(make_group())
    assert event["schema_version"] == 1
    assert event["event_type"] == "diagnostic.new"
    assert event["severity"] == "HIGH"
    assert event["source"] == {"file": "gamemodes/rp.pwn", "line": 42}
    assert event["presentation"] == {"file_color": "red", "line_color": "blue"}
    assert "gamemodes/rp.pwn:42" in event["summary"]


@pytest.mark.parametrize(
    ("kind", "severity"),
    [("crash", "CRITICAL"), ("runtime_error", "HIGH"), ("long_call", "MEDIUM")],
)
def test_alert_severity_mapping(kind: EventKind, severity: str) -> None:
    event = build_alert_event(make_group(kind=kind))
    assert event["severity"] == severity


def test_template_customizes_summary_but_cannot_replace_structured_location() -> None:
    event = build_alert_event(make_group(), template="OWNER NOTICE: {message}")
    assert event["summary"] == "OWNER NOTICE: Array index out of bounds"
    assert event["source"] == {"file": "gamemodes/rp.pwn", "line": 42}


def test_jsonl_record_is_valid_utf8_json_with_one_trailing_newline() -> None:
    raw = serialize_alert_event(make_group(message="Kesalahan café"))
    assert raw.endswith("\n")
    assert raw.count("\n") == 1
    parsed = json.loads(raw)
    assert parsed["summary"].endswith("Kesalahan café")


@pytest.mark.parametrize(
    "template",
    [
        "{message.__class__}",
        "{unknown}",
        "{message!r}",
        "{message:>4}",
        "{message",
        "first line\nsecond line",
    ],
)
def test_invalid_template_is_rejected(template: str) -> None:
    with pytest.raises(InputError):
        build_alert_event(make_group(), template=template)


def test_alert_prefix_cannot_contain_control_characters() -> None:
    with pytest.raises(InputError, match="single line"):
        build_alert_event(make_group(), prefix="bad\nadmin")


def test_untrusted_log_text_is_sanitized_before_becoming_alert_data() -> None:
    event = build_alert_event(
        make_group(message="bad\n[BLUE] message", file="rp.pwn\n[RED]:999")
    )
    source = event["source"]
    assert isinstance(source, dict)
    assert "\n" not in str(source["file"])
    assert "\n" not in str(event["summary"])
    assert "rp.pwn? [RED]:999" not in str(source["file"])


def test_append_creates_private_jsonl_file_and_preserves_prior_records(tmp_path: Path) -> None:
    target = tmp_path / "alerts.jsonl"
    append_alert_event(str(target), make_group())
    append_alert_event(str(target), make_group(kind="crash"))
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["kind"] == "runtime_error"
    assert json.loads(lines[1])["kind"] == "crash"
    if os.name == "posix":
        assert target.stat().st_mode & 0o777 == 0o600


def test_append_refuses_symlink_without_modifying_its_target(tmp_path: Path) -> None:
    target = tmp_path / "real.jsonl"
    target.write_text("keep\n", encoding="utf-8")
    link = tmp_path / "alerts.jsonl"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable on this runner")
    with pytest.raises(Exception, match="symbolic link"):
        append_alert_event(str(link), make_group())
    assert target.read_text(encoding="utf-8") == "keep\n"


def test_append_refuses_hard_link_without_modifying_file(tmp_path: Path) -> None:
    target = tmp_path / "real.jsonl"
    target.write_text("keep\n", encoding="utf-8")
    link = tmp_path / "another-name.jsonl"
    try:
        os.link(target, link)
    except OSError:
        pytest.skip("hard links are unavailable on this runner")
    with pytest.raises(Exception, match="hard links"):
        append_alert_event(str(target), make_group())
    assert target.read_text(encoding="utf-8") == "keep\n"


def test_sink_disables_itself_after_a_write_failure(tmp_path: Path) -> None:
    sink = JsonlAlertSink(str(tmp_path))
    assert sink.emit(make_group()) is False
    assert sink.disabled is True
    assert sink.failure_reason is not None
    assert sink.emit(make_group()) is False
    assert sink.failure_reason is not None


def test_default_template_has_location_and_message_placeholders() -> None:
    assert "{file}" in DEFAULT_ALERT_TEMPLATE
    assert "{line}" in DEFAULT_ALERT_TEMPLATE
    assert "{message}" in DEFAULT_ALERT_TEMPLATE
