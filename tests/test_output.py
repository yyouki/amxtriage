import os
import stat
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from amxtriage import cli
from amxtriage import output as output_module
from amxtriage.errors import AmxTriageError, OutputError
from amxtriage.output import write_text_file

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX behaviour only")


@pytest.fixture
def umask_022() -> Iterator[None]:
    previous = os.umask(0o022)
    try:
        yield
    finally:
        os.umask(previous)


def test_a_new_file_receives_the_text(tmp_path: Path) -> None:
    target = tmp_path / "report.txt"
    write_text_file(str(target), "first line\nsecond line \u00e9\u4e2d\n")
    assert target.read_bytes() == "first line\nsecond line \u00e9\u4e2d\n".encode()


@posix_only
def test_a_new_file_gets_the_mode_allowed_by_the_umask(tmp_path: Path, umask_022: None) -> None:
    target = tmp_path / "report.txt"
    write_text_file(str(target), "x")
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


@posix_only
def test_a_stricter_umask_gives_a_stricter_mode(tmp_path: Path) -> None:
    previous = os.umask(0o077)
    try:
        write_text_file(str(tmp_path / "report.txt"), "x")
    finally:
        os.umask(previous)
    assert stat.S_IMODE((tmp_path / "report.txt").stat().st_mode) == 0o600


def test_an_existing_file_is_replaced_without_leaving_old_text(tmp_path: Path) -> None:
    target = tmp_path / "report.txt"
    target.write_text("old text that is much longer than the new text\n" * 20)
    write_text_file(str(target), "new\n")
    assert target.read_text() == "new\n"


@posix_only
def test_an_existing_file_keeps_its_mode_and_identity(tmp_path: Path) -> None:
    target = tmp_path / "report.txt"
    target.write_text("old")
    target.chmod(0o640)
    before = target.stat()
    write_text_file(str(target), "new")
    after = target.stat()
    assert stat.S_IMODE(after.st_mode) == 0o640
    assert after.st_ino == before.st_ino


@posix_only
def test_a_symbolic_link_is_refused_and_its_target_is_left_alone(tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("IMPORTANT\n")
    link = tmp_path / "report.md"
    link.symlink_to(victim)
    with pytest.raises(OutputError, match="is a symbolic link; refusing to write through it"):
        write_text_file(str(link), "overwritten")
    assert victim.read_text() == "IMPORTANT\n"
    assert link.is_symlink()


@posix_only
def test_a_dangling_symbolic_link_creates_nothing(tmp_path: Path) -> None:
    link = tmp_path / "report.md"
    link.symlink_to(tmp_path / "created_through_the_link.txt")
    with pytest.raises(OutputError, match="symbolic link"):
        write_text_file(str(link), "x")
    assert not (tmp_path / "created_through_the_link.txt").exists()


@posix_only
def test_a_symbolic_link_to_a_directory_is_refused(tmp_path: Path) -> None:
    (tmp_path / "folder").mkdir()
    link = tmp_path / "report.md"
    link.symlink_to(tmp_path / "folder", target_is_directory=True)
    with pytest.raises(OutputError, match="symbolic link"):
        write_text_file(str(link), "x")


@posix_only
def test_a_file_in_a_symlinked_folder_is_still_written(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "alias").symlink_to(tmp_path / "real", target_is_directory=True)
    write_text_file(str(tmp_path / "alias" / "report.md"), "inside")
    assert (tmp_path / "real" / "report.md").read_text() == "inside"


@posix_only
def test_a_file_with_several_hard_links_is_refused_and_untouched(tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("IMPORTANT\n")
    other = tmp_path / "report.md"
    os.link(victim, other)
    with pytest.raises(OutputError, match="2 hard links"):
        write_text_file(str(other), "overwritten")
    assert victim.read_text() == "IMPORTANT\n"
    assert other.read_text() == "IMPORTANT\n"


@posix_only
def test_a_file_that_is_no_longer_linked_elsewhere_is_accepted(tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("old")
    other = tmp_path / "report.md"
    os.link(victim, other)
    victim.unlink()
    write_text_file(str(other), "new")
    assert other.read_text() == "new"


@posix_only
def test_a_device_file_can_still_be_written(tmp_path: Path) -> None:
    if not Path(os.devnull).exists():
        pytest.skip("no null device")
    write_text_file(os.devnull, "discarded")
    assert stat.S_ISCHR(os.stat(os.devnull).st_mode)


@posix_only
def test_a_full_device_is_reported_as_a_clean_error() -> None:
    if not Path("/dev/full").exists():
        pytest.skip("no /dev/full on this system")
    with pytest.raises(OutputError, match="No space left on device"):
        write_text_file("/dev/full", "x")


def test_a_directory_is_a_clean_error(tmp_path: Path) -> None:
    with pytest.raises(OutputError, match="cannot write"):
        write_text_file(str(tmp_path), "x")


def test_a_missing_folder_is_a_clean_error(tmp_path: Path) -> None:
    with pytest.raises(OutputError, match="No such file or directory"):
        write_text_file(str(tmp_path / "missing" / "report.md"), "x")


def test_the_error_names_the_path_and_the_reason(tmp_path: Path) -> None:
    target = tmp_path / "missing" / "report.md"
    with pytest.raises(OutputError) as caught:
        write_text_file(str(target), "x")
    assert str(caught.value) == f"cannot write '{target}': No such file or directory"


def test_output_errors_are_ordinary_amxtriage_errors() -> None:
    assert issubclass(OutputError, AmxTriageError)


@posix_only
def test_without_nofollow_support_a_symbolic_link_is_followed_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(output_module, "_NOFOLLOW", 0)
    victim = tmp_path / "victim.txt"
    victim.write_text("old")
    link = tmp_path / "report.md"
    link.symlink_to(victim)
    write_text_file(str(link), "new")
    assert victim.read_text() == "new"


@posix_only
def test_the_cli_refuses_a_symbolic_link_and_prints_a_clean_error(
    tmp_path: Path, sample_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("IMPORTANT\n")
    link = tmp_path / "report.md"
    link.symlink_to(victim)
    code = cli.main(["analyze", str(sample_log), "-o", str(link)])
    captured = capsys.readouterr()
    assert code == cli.EXIT_ERROR
    assert captured.out == ""
    assert "cannot write" in captured.err
    assert "symbolic link" in captured.err
    assert victim.read_text() == "IMPORTANT\n"


@posix_only
def test_the_cli_refuses_a_hard_linked_file(
    tmp_path: Path, sample_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("IMPORTANT\n")
    other = tmp_path / "report.md"
    os.link(victim, other)
    code = cli.main(["analyze", str(sample_log), "-o", str(other)])
    assert code == cli.EXIT_ERROR
    assert "hard links" in capsys.readouterr().err
    assert victim.read_text() == "IMPORTANT\n"


@posix_only
def test_the_cli_error_for_a_hostile_file_name_is_sanitized(
    tmp_path: Path, sample_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    link = tmp_path / "evil\x1b[31m\u202e.md"
    link.symlink_to(tmp_path / "victim.txt")
    code = cli.main(["analyze", str(sample_log), "-o", str(link)])
    err = capsys.readouterr().err
    assert code == cli.EXIT_ERROR
    assert "\x1b" not in err
    assert "\u202e" not in err
    assert "evil?[31m?.md" in err


def test_the_cli_still_writes_a_report_to_a_new_file(
    tmp_path: Path, sample_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "report.md"
    code = cli.main(["analyze", str(sample_log), "--format", "markdown", "-o", str(target)])
    assert code == cli.EXIT_OK
    assert capsys.readouterr().out == ""
    assert target.read_text(encoding="utf-8").startswith("# amxtriage report")


@posix_only
def test_a_baseline_is_still_written_by_replacing_a_symbolic_link(
    tmp_path: Path, sample_log: Path
) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("IMPORTANT\n")
    link = tmp_path / "baseline.json"
    link.symlink_to(victim)
    assert cli.main(["analyze", str(sample_log), "--save-baseline", str(link)]) == cli.EXIT_OK
    assert victim.read_text() == "IMPORTANT\n"
    assert not link.is_symlink()
    assert '"signatures"' in link.read_text()


@posix_only
def test_a_baseline_is_still_written_by_replacing_a_hard_linked_file(
    tmp_path: Path, sample_log: Path
) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("IMPORTANT\n")
    other = tmp_path / "baseline.json"
    os.link(victim, other)
    assert cli.main(["analyze", str(sample_log), "--save-baseline", str(other)]) == cli.EXIT_OK
    assert victim.read_text() == "IMPORTANT\n"
    assert '"signatures"' in other.read_text()
