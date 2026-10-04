import json

import pytest

from amxtriage import baseline as baseline_module
from amxtriage.analysis import analyze_logs
from amxtriage.baseline import SCHEMA_VERSION, load_baseline, save_baseline
from amxtriage.errors import BaselineError


def groups_of(sample_log):
    return analyze_logs([str(sample_log)]).aggregator.sorted_groups()


def test_save_then_load_round_trips_all_signature_ids(sample_log, tmp_path):
    groups = groups_of(sample_log)
    path = tmp_path / "baseline.json"
    assert save_baseline(str(path), groups) == len(groups)
    assert load_baseline(str(path)) == frozenset(group.signature_id for group in groups)


def test_saved_file_has_documented_structure(sample_log, tmp_path):
    path = tmp_path / "baseline.json"
    save_baseline(str(path), groups_of(sample_log))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tool"] == "amxtriage"
    assert data["schema_version"] == SCHEMA_VERSION
    assert {"id", "kind", "code", "function", "count"} <= set(data["signatures"][0])


def test_saving_leaves_no_temporary_files_behind(sample_log, tmp_path):
    save_baseline(str(tmp_path / "baseline.json"), groups_of(sample_log))
    assert [entry.name for entry in tmp_path.iterdir()] == ["baseline.json"]


def test_saving_overwrites_an_existing_baseline(sample_log, tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text("old content")
    save_baseline(str(path), groups_of(sample_log))
    assert load_baseline(str(path))


def test_saving_into_a_missing_directory_raises_baseline_error(sample_log, tmp_path):
    with pytest.raises(BaselineError, match="cannot write baseline"):
        save_baseline(str(tmp_path / "missing" / "baseline.json"), groups_of(sample_log))


def test_saving_an_empty_baseline_is_valid(tmp_path):
    path = tmp_path / "empty.json"
    assert save_baseline(str(path), []) == 0
    assert load_baseline(str(path)) == frozenset()


def test_missing_baseline_file_is_a_clear_error(tmp_path):
    with pytest.raises(BaselineError, match="does not exist"):
        load_baseline(str(tmp_path / "nope.json"))


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("not json at all", "cannot read baseline"),
        ("[]", "not an amxtriage baseline"),
        ('{"tool": "other", "schema_version": 1, "signatures": []}', "not an amxtriage baseline"),
        (
            '{"tool": "amxtriage", "schema_version": 99, "signatures": []}',
            "unsupported schema_version",
        ),
        ('{"tool": "amxtriage", "schema_version": 1}', "no valid 'signatures'"),
        ('{"tool": "amxtriage", "schema_version": 1, "signatures": "x"}', "no valid 'signatures'"),
        ('{"tool": "amxtriage", "schema_version": 1, "signatures": [1]}', "invalid signature id"),
        ('{"tool": "amxtriage", "schema_version": 1, "signatures": [{"id": "short"}]}', "invalid"),
        (
            '{"tool": "amxtriage", "schema_version": 1, "signatures": [{"id": "ZZZZZZZZZZZZ"}]}',
            "invalid",
        ),
        (
            '{"tool": "amxtriage", "schema_version": 1, "signatures": [{"id": 123456789012}]}',
            "invalid",
        ),
    ],
)
def test_malformed_baselines_are_rejected_with_specific_messages(tmp_path, content, message):
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(BaselineError, match=message):
        load_baseline(str(path))


def test_non_utf8_baseline_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"\xff\xfe\x00\x00")
    with pytest.raises(BaselineError, match="cannot read baseline"):
        load_baseline(str(path))


def test_deeply_nested_json_cannot_crash_the_loader(tmp_path):
    path = tmp_path / "bomb.json"
    path.write_text("[" * 100000 + "]" * 100000, encoding="utf-8")
    with pytest.raises(BaselineError):
        load_baseline(str(path))


def test_oversized_baseline_is_refused_before_reading(tmp_path, monkeypatch):
    monkeypatch.setattr(baseline_module, "MAX_BASELINE_BYTES", 10)
    path = tmp_path / "big.json"
    path.write_text("x" * 100)
    with pytest.raises(BaselineError, match="larger than"):
        load_baseline(str(path))


def test_directory_given_as_baseline_is_a_clean_error(tmp_path):
    with pytest.raises(BaselineError):
        load_baseline(str(tmp_path))
