import json

from amxtriage.aggregate import Aggregator
from amxtriage.analysis import analyze_logs, build_report
from amxtriage.cli import main
from amxtriage.model import Event
from amxtriage.recommendation import recommend_group
from helpers import error_block


def write_log(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def test_recommend_reports_tailored_array_bounds_guidance(tmp_path, capsys):
    log = write_log(tmp_path / "server.log", error_block(4, line=30))
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    source_lines = ["// source context"] * 29 + ["PlayerScores[slot] += 1;"] + ["return 1;"] * 10
    source = source_dir / "rp.pwn"
    original_source = "\n".join(source_lines) + "\n"
    source.write_text(original_source, encoding="utf-8")

    code = main(["recommend", log, "--source-dir", str(source_dir)])
    out = capsys.readouterr().out

    assert code == 0
    assert "Array index out of bounds" in out
    assert "index >= 0 && index < sizeof values" in out
    assert "Automatic fix: unavailable" in out
    assert "Source context:" in out
    assert "No source files were modified" in out
    assert source.read_text(encoding="utf-8") == original_source


def test_suggest_alias_can_emit_json(tmp_path, capsys):
    log = write_log(tmp_path / "server.log", error_block(11, message="Divide by zero"))
    code = main(["suggest", log, "--format", "json"])
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert code == 0
    assert payload["mode"] == "rule-based-recommendations"
    assert payload["automatic_changes_applied"] is False
    assert payload["problems"][0]["title"] == "Divide by zero"
    assert payload["problems"][0]["automatic_fix_available"] is False
    assert "divisor != 0" in payload["problems"][0]["example"]


def test_recommend_respects_top_and_min_count(tmp_path, capsys):
    lines = error_block(4, function="OnPlayerUpdate", line=30)
    lines += error_block(4, function="OnPlayerUpdate", line=30)
    lines += error_block(11, function="OnPlayerCommandText", line=50, message="Divide by zero")
    log = write_log(tmp_path / "server.log", lines)
    code = main(["recommend", log, "--top", "1", "--min-count", "2"])
    out = capsys.readouterr().out

    assert code == 0
    assert "Array index out of bounds" in out
    assert "Divide by zero" not in out


def test_recommendation_fallback_is_explicit_about_uncertainty():
    report = build_report(analyze_logs([]), top=20)
    assert report.groups == []
    # The CLI handles empty input reports; group-level fallback behaviour is covered
    # through runtime codes without a specialised rule below.
    aggregator = Aggregator()
    event = Event(
        kind="runtime_error",
        line_number=1,
        timestamp=None,
        code=6,
        message="Invalid instruction",
        script=None,
        details=(),
        frames=(),
        native_frames=(),
    )
    added = aggregator.add(event, "server.log")
    assert added.group is not None
    suggestion = recommend_group(added.group)
    assert suggestion.confidence == "low"
    assert "not proof" in suggestion.diagnosis
    assert suggestion.automatic_fix is False
