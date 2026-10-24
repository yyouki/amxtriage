import contextlib
import dataclasses
import os
import shutil
import signal
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import FrameType

import pytest

from amxtriage import source as source_module
from amxtriage.source import SourceIndex

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="needs POSIX signals, links and named pipes"
)

SECRET = "TOP SECRET FROM OUTSIDE THE SOURCE DIRECTORY"
NUMBERED = "".join(f"line {number}\n" for number in range(1, 21))
DESCRIPTORS = Path("/proc/self/fd")


class Hang(BaseException):
    pass


@contextlib.contextmanager
def deadline(seconds: float = 5.0) -> Iterator[None]:
    def on_alarm(_number: int, _frame: FrameType | None) -> None:
        raise Hang(f"blocked for more than {seconds} seconds")

    previous = signal.signal(signal.SIGALRM, on_alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


@dataclass(frozen=True)
class Layout:
    root: Path
    outside: Path

    @property
    def target(self) -> Path:
        return self.root / "mods" / "rp.pwn"


@pytest.fixture
def layout(tmp_path: Path) -> Layout:
    root = tmp_path / "src"
    (root / "mods").mkdir(parents=True)
    target = root / "mods" / "rp.pwn"
    target.write_text(NUMBERED, encoding="utf-8")
    outside = tmp_path / "outside"
    (outside / "same").mkdir(parents=True)
    (outside / "same_root" / "mods").mkdir(parents=True)
    (outside / "secret.txt").write_text(SECRET + "\n" * 25, encoding="utf-8")
    (outside / "rp.pwn").write_text(SECRET + "\n" * 25, encoding="utf-8")
    os.link(target, outside / "same" / "rp.pwn")
    os.link(target, outside / "same_root" / "mods" / "rp.pwn")
    return Layout(root, outside)


Action = Callable[[Layout], None]


def to_symlink_outside(layout: Layout) -> None:
    layout.target.unlink()
    layout.target.symlink_to(layout.outside / "secret.txt")


def to_hard_link_outside(layout: Layout) -> None:
    layout.target.unlink()
    os.link(layout.outside / "secret.txt", layout.target)


def directory_to_symlink_outside(layout: Layout) -> None:
    shutil.rmtree(layout.root / "mods")
    (layout.root / "mods").symlink_to(layout.outside, target_is_directory=True)


def to_fifo(layout: Layout) -> None:
    layout.target.unlink()
    os.mkfifo(layout.target)


def to_other_file(layout: Layout) -> None:
    layout.target.unlink()
    layout.target.write_text("REPLACEMENT\n" * 30, encoding="utf-8")


def to_symlink_to_the_same_file(layout: Layout) -> None:
    layout.target.unlink()
    layout.target.symlink_to(layout.outside / "same" / "rp.pwn")


def directory_to_symlink_to_the_same_file(layout: Layout) -> None:
    shutil.rmtree(layout.root / "mods")
    (layout.root / "mods").symlink_to(layout.outside / "same", target_is_directory=True)


def root_to_symlink_to_the_same_file(layout: Layout) -> None:
    layout.root.rename(layout.root.with_name("src_moved"))
    layout.root.symlink_to(layout.outside / "same_root", target_is_directory=True)


def to_directory(layout: Layout) -> None:
    layout.target.unlink()
    layout.target.mkdir()


LEAKING_SWAPS: dict[str, Action] = {
    "symlink_to_a_secret": to_symlink_outside,
    "hard_link_to_a_secret": to_hard_link_outside,
    "directory_symlinked_to_a_secret": directory_to_symlink_outside,
    "named_pipe": to_fifo,
    "another_regular_file": to_other_file,
    "directory": to_directory,
}

LINK_SWAPS: dict[str, Action] = {
    "symlink_to_the_same_file": to_symlink_to_the_same_file,
    "directory_symlink_to_the_same_file": directory_to_symlink_to_the_same_file,
    "root_symlink_to_the_same_file": root_to_symlink_to_the_same_file,
}


def swap_after_check(monkeypatch: pytest.MonkeyPatch, action: Callable[[], None]) -> None:
    original = SourceIndex._checked_path

    def checked(self: SourceIndex, parts: tuple[str, ...]) -> object:
        result = original(self, parts)
        action()
        return result

    monkeypatch.setattr(SourceIndex, "_checked_path", checked)


def without_anchoring(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(source_module, "_ANCHORED", False)
    monkeypatch.setattr(source_module, "_NOFOLLOW", 0)


def verified_file(layout: Layout) -> tuple[SourceIndex, source_module._Verified]:
    index = SourceIndex(str(layout.root))
    verified = index._checked_path(("mods", "rp.pwn"))
    assert verified is not None
    return index, verified


def open_descriptors() -> int:
    return len(os.listdir(DESCRIPTORS))


class ScriptedStream:
    def __init__(self, lines: list[bytes], endless_line: bool = False) -> None:
        self.lines = iter(lines)
        self.endless_line = endless_line
        self.sizes: list[int] = []

    def readline(self, size: int = -1) -> bytes:
        self.sizes.append(size)
        if self.endless_line:
            return b"x" * size
        return next(self.lines, b"")

    def __enter__(self) -> "ScriptedStream":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def test_without_a_swap_the_snippet_is_returned(layout: Layout) -> None:
    snippet = SourceIndex(str(layout.root)).snippet("mods/rp.pwn", 3, 2)
    assert snippet is not None
    assert snippet.path == "mods/rp.pwn"
    assert snippet.lines == ("line 1", "line 2", "line 3", "line 4", "line 5")


@pytest.mark.parametrize("name", sorted(LEAKING_SWAPS))
def test_a_file_swapped_in_after_the_check_is_never_read(
    layout: Layout, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    index = SourceIndex(str(layout.root))
    swap_after_check(monkeypatch, lambda: LEAKING_SWAPS[name](layout))
    with deadline():
        assert index.snippet("mods/rp.pwn", 3, 2) is None


@pytest.mark.parametrize("name", sorted(LINK_SWAPS))
def test_a_link_is_not_followed_even_when_it_leads_to_the_checked_file(
    layout: Layout, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    index = SourceIndex(str(layout.root))
    swap_after_check(monkeypatch, lambda: LINK_SWAPS[name](layout))
    with deadline():
        assert index.snippet("mods/rp.pwn", 3, 2) is None


@pytest.mark.parametrize(
    "name",
    [
        "symlink_to_a_secret",
        "hard_link_to_a_secret",
        "directory_symlinked_to_a_secret",
        "named_pipe",
        "another_regular_file",
    ],
)
def test_the_portable_fallback_still_refuses_swaps_by_comparing_identities(
    layout: Layout, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    without_anchoring(monkeypatch)
    index = SourceIndex(str(layout.root))
    swap_after_check(monkeypatch, lambda: LEAKING_SWAPS[name](layout))
    with deadline():
        assert index.snippet("mods/rp.pwn", 3, 2) is None


def test_the_portable_fallback_cannot_tell_a_link_to_the_same_file_apart(
    layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    without_anchoring(monkeypatch)
    index = SourceIndex(str(layout.root))
    swap_after_check(monkeypatch, lambda: to_symlink_to_the_same_file(layout))
    snippet = index.snippet("mods/rp.pwn", 3, 2)
    assert snippet is not None
    assert snippet.lines[2] == "line 3"


def test_the_fallback_keeps_refusing_a_final_symlink_when_the_platform_has_nofollow(
    layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(source_module, "_ANCHORED", False)
    index = SourceIndex(str(layout.root))
    swap_after_check(monkeypatch, lambda: to_symlink_to_the_same_file(layout))
    assert index.snippet("mods/rp.pwn", 3, 2) is None


def test_an_inside_symlink_resolved_at_check_time_is_still_allowed(tmp_path: Path) -> None:
    root = tmp_path / "src"
    (root / "real").mkdir(parents=True)
    (root / "real" / "rp.pwn").write_text(NUMBERED, encoding="utf-8")
    (root / "alias.pwn").symlink_to(root / "real" / "rp.pwn")
    snippet = SourceIndex(str(root)).snippet("alias.pwn", 2, 1)
    assert snippet is not None
    assert snippet.path == "real/rp.pwn"
    assert snippet.lines == ("line 1", "line 2", "line 3")


def test_the_descriptor_of_a_regular_file_reads_the_checked_content(layout: Layout) -> None:
    index, verified = verified_file(layout)
    handle = index._open_verified(verified)
    assert handle is not None
    with handle:
        assert handle.read() == NUMBERED.encode("utf-8")


def test_a_named_pipe_is_refused_without_blocking(layout: Layout) -> None:
    index, verified = verified_file(layout)
    to_fifo(layout)
    with deadline():
        assert index._open_verified(verified) is None


def test_a_named_pipe_is_refused_even_when_no_inode_is_known(layout: Layout) -> None:
    index, verified = verified_file(layout)
    to_fifo(layout)
    with deadline():
        assert index._open_verified(dataclasses.replace(verified, inode=0)) is None


def test_a_directory_is_refused(layout: Layout) -> None:
    index, verified = verified_file(layout)
    to_directory(layout)
    assert index._open_verified(verified) is None


def test_a_file_that_grew_beyond_the_limit_is_refused(
    layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    index, verified = verified_file(layout)
    monkeypatch.setattr(source_module, "MAX_SOURCE_BYTES", len(NUMBERED) - 1)
    assert index._open_verified(verified) is None


def test_a_file_of_exactly_the_limit_is_accepted(
    layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(source_module, "MAX_SOURCE_BYTES", len(NUMBERED))
    index, verified = verified_file(layout)
    handle = index._open_verified(verified)
    assert handle is not None
    handle.close()


def test_a_replacement_file_is_refused_because_its_identity_differs(layout: Layout) -> None:
    index, verified = verified_file(layout)
    to_other_file(layout)
    assert index._open_verified(verified) is None


def test_identities_are_not_compared_when_the_file_system_reports_no_inode(layout: Layout) -> None:
    index, verified = verified_file(layout)
    to_other_file(layout)
    handle = index._open_verified(dataclasses.replace(verified, inode=0))
    assert handle is not None
    with handle:
        assert handle.readline() == b"REPLACEMENT\n"


def test_a_file_of_another_device_is_refused(layout: Layout) -> None:
    index, verified = verified_file(layout)
    assert index._open_verified(dataclasses.replace(verified, device=verified.device + 1)) is None


def test_a_file_that_vanished_is_refused(layout: Layout) -> None:
    index, verified = verified_file(layout)
    layout.target.unlink()
    assert index._open_verified(verified) is None


def test_an_endless_line_is_read_in_one_bounded_call(
    layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(source_module, "MAX_SOURCE_BYTES", 1000)
    stream = ScriptedStream([], endless_line=True)
    monkeypatch.setattr(SourceIndex, "_open_verified", lambda _self, _verified: stream)
    assert SourceIndex(str(layout.root)).snippet("mods/rp.pwn", 3, 2) is None
    assert stream.sizes == [1001]


def test_many_short_lines_are_counted_against_the_total_limit(
    layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(source_module, "MAX_SOURCE_BYTES", 1000)
    stream = ScriptedStream([b"123456789\n"] * 500)
    monkeypatch.setattr(SourceIndex, "_open_verified", lambda _self, _verified: stream)
    assert SourceIndex(str(layout.root)).snippet("mods/rp.pwn", 300, 2) is None
    assert len(stream.sizes) == 101


def test_a_file_that_fills_the_limit_exactly_can_still_be_read(
    layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(source_module, "MAX_SOURCE_BYTES", len(NUMBERED))
    snippet = SourceIndex(str(layout.root)).snippet("mods/rp.pwn", 20, 2)
    assert snippet is not None
    assert snippet.lines == ("line 18", "line 19", "line 20")


def test_reading_stops_at_the_last_line_that_is_needed(
    layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream = ScriptedStream([f"line {number}\n".encode() for number in range(1, 100)])
    monkeypatch.setattr(SourceIndex, "_open_verified", lambda _self, _verified: stream)
    snippet = SourceIndex(str(layout.root)).snippet("mods/rp.pwn", 5, 2)
    assert snippet is not None
    assert snippet.lines == ("line 3", "line 4", "line 5", "line 6", "line 7")
    assert len(stream.sizes) == 7


def test_a_read_error_while_reading_yields_no_snippet(
    layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Failing(ScriptedStream):
        def readline(self, size: int = -1) -> bytes:
            raise OSError(5, "Input/output error")

    monkeypatch.setattr(SourceIndex, "_open_verified", lambda _self, _verified: Failing([]))
    assert SourceIndex(str(layout.root)).snippet("mods/rp.pwn", 3, 2) is None


@pytest.mark.skipif(not DESCRIPTORS.is_dir(), reason="needs /proc/self/fd")
@pytest.mark.parametrize("name", [*sorted(LEAKING_SWAPS), *sorted(LINK_SWAPS)])
def test_refused_files_leave_no_descriptor_open(layout: Layout, name: str) -> None:
    index, verified = verified_file(layout)
    {**LEAKING_SWAPS, **LINK_SWAPS}[name](layout)
    before = open_descriptors()
    with deadline():
        for _ in range(60):
            assert index._open_verified(verified) is None
    assert open_descriptors() == before


@pytest.mark.skipif(not DESCRIPTORS.is_dir(), reason="needs /proc/self/fd")
def test_accepted_files_leave_no_descriptor_open_once_closed(layout: Layout) -> None:
    index, verified = verified_file(layout)
    before = open_descriptors()
    for _ in range(60):
        handle = index._open_verified(verified)
        assert handle is not None
        handle.close()
    assert open_descriptors() == before


@pytest.mark.skipif(not DESCRIPTORS.is_dir(), reason="needs /proc/self/fd")
def test_snippets_leave_no_descriptor_open(layout: Layout) -> None:
    index = SourceIndex(str(layout.root))
    before = open_descriptors()
    for _ in range(60):
        assert index.snippet("mods/rp.pwn", 3, 2) is not None
    assert open_descriptors() == before


def test_anchoring_is_available_on_this_platform() -> None:
    assert source_module._ANCHORED is True
