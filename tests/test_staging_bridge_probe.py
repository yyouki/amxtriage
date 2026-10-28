import os
import stat
from pathlib import Path

import pytest
from scripts.staging_bridge_probe import PROBE_RECORD, ProbeError, append_probe, main


def test_probe_defaults_to_dry_run_without_touching_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "alerts.txt"

    assert main([str(target)]) == 0

    assert not target.exists()
    assert "DRY RUN" in capsys.readouterr().out


def test_probe_appends_single_synthetic_record_and_keeps_existing_content(tmp_path: Path) -> None:
    target = tmp_path / "alerts.txt"
    original = "existing-record\n"
    target.write_text(original, encoding="ascii")

    append_probe(target)

    assert target.read_text(encoding="ascii") == original + PROBE_RECORD
    assert PROBE_RECORD.count("\n") == 1


def test_probe_creates_new_file_with_private_permissions(tmp_path: Path) -> None:
    target = tmp_path / "alerts.txt"

    append_probe(target)

    assert target.read_text(encoding="ascii") == PROBE_RECORD
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_send_requires_explicit_staging_confirmation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "alerts.txt"

    assert main([str(target), "--send"]) == 2

    assert not target.exists()
    assert "--confirm-staging" in capsys.readouterr().err


def test_probe_refuses_symbolic_link(tmp_path: Path) -> None:
    target = tmp_path / "alerts.txt"
    target.write_text("original\n", encoding="ascii")
    link = tmp_path / "alerts-link.txt"
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError):
        pytest.skip("symbolic links are unavailable on this platform")

    with pytest.raises(ProbeError, match=r"symbolic link|open alert file"):
        append_probe(link)

    assert target.read_text(encoding="ascii") == "original\n"


def test_probe_refuses_hard_link_target(tmp_path: Path) -> None:
    target = tmp_path / "alerts.txt"
    target.write_text("original\n", encoding="ascii")
    link = tmp_path / "alerts-hardlink.txt"
    try:
        os.link(target, link)
    except (NotImplementedError, OSError):
        pytest.skip("hard links are unavailable on this platform")

    with pytest.raises(ProbeError, match="hard links"):
        append_probe(link)

    assert target.read_text(encoding="ascii") == "original\n"


def test_probe_rejects_directory_target(tmp_path: Path) -> None:
    with pytest.raises(ProbeError):
        append_probe(tmp_path)
