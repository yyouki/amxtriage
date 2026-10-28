from pathlib import Path

import pytest

from amxtriage.errors import InputError
from amxtriage.gui import analyze_for_gui


def test_gui_analyzer_renders_local_log_without_changing_it() -> None:
    log_path = Path("examples/sample_server_log.txt")
    before = log_path.read_bytes()

    report = analyze_for_gui(str(log_path), language="en")

    assert "input" in report.lower()
    assert "result" in report.lower()
    assert log_path.read_bytes() == before


def test_gui_analyzer_rejects_unsupported_language() -> None:
    with pytest.raises(InputError, match="unsupported language"):
        analyze_for_gui("examples/sample_server_log.txt", language="xx")


def test_gui_analyzer_rejects_missing_log() -> None:
    with pytest.raises(InputError, match="not a readable regular log file"):
        analyze_for_gui("does-not-exist.log")


def test_gui_analyzer_supports_indonesian_report() -> None:
    report = analyze_for_gui("examples/sample_server_log.txt", language="id")
    assert "masukan" in report.lower() or "input" in report.lower()
