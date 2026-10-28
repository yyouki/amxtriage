import contextlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from amxtriage.errors import SourceError
from amxtriage.textutil import sanitize

MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_INDEXED_FILES = 50_000
MAX_SCANNED_DIRECTORIES = 20_000
MAX_CONTEXT_RADIUS = 20
MAX_SOURCE_LINE_CHARS = 200
SOURCE_SUFFIXES = frozenset({".pwn", ".inc", ".p", ".pawn"})
SKIPPED_DIRECTORIES = frozenset({".git", "node_modules", "__pycache__"})

_SEPARATORS = re.compile(r"[\\/]+")
_DRIVE = re.compile(r"[A-Za-z]:")

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_FILE_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_NOCTTY", 0)
    | getattr(os, "O_BINARY", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_ANCHORED = bool(_NOFOLLOW and _DIRECTORY and os.open in os.supports_dir_fd)


@dataclass(frozen=True, slots=True)
class Snippet:
    path: str
    first_line: int
    target_line: int
    lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Verified:
    path: Path
    parts: tuple[str, ...]
    device: int
    inode: int


def _is_acceptable(info: os.stat_result) -> bool:
    return stat.S_ISREG(info.st_mode) and info.st_size <= MAX_SOURCE_BYTES


def _is_checked_file(info: os.stat_result, verified: _Verified) -> bool:
    if not _is_acceptable(info):
        return False
    if verified.inode and info.st_ino:
        return (info.st_dev, info.st_ino) == (verified.device, verified.inode)
    return True


def path_components(logged_path: str) -> list[str]:
    parts = [part for part in _SEPARATORS.split(logged_path) if part and part not in (".", "..")]
    if parts and _DRIVE.fullmatch(parts[0]):
        parts = parts[1:]
    return parts


class SourceIndex:
    def __init__(self, root: str) -> None:
        try:
            resolved = Path(root).resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise SourceError(f"source directory '{root}' cannot be used: {error}") from error
        if not resolved.is_dir():
            raise SourceError(f"source directory '{root}' is not a directory")
        self._root = resolved
        self._files: dict[str, list[tuple[str, ...]]] = {}
        self._scan()

    @property
    def root(self) -> Path:
        """Return the canonical source root used for safe, root-confined operations."""
        return self._root

    @property
    def file_count(self) -> int:
        return sum(len(paths) for paths in self._files.values())

    def find(self, logged_path: str) -> Path | None:
        verified = self._locate(logged_path)
        return verified.path if verified is not None else None

    def read_bytes(self, logged_path: str) -> tuple[str, bytes] | None:
        """Read a bounded source file using the same verified, no-follow open as snippets.

        The returned path is relative to the configured source root. A path from a log is
        used only for matching against the pre-indexed root; it is never opened directly.
        """
        verified = self._locate(logged_path)
        if verified is None:
            return None
        handle = self._open_verified(verified)
        if handle is None:
            return None
        try:
            with handle:
                content = handle.read(MAX_SOURCE_BYTES + 1)
        except OSError:
            return None
        if len(content) > MAX_SOURCE_BYTES:
            return None
        return "/".join(verified.parts), content

    def _locate(self, logged_path: str) -> _Verified | None:
        parts = path_components(logged_path)
        if not parts:
            return None
        candidates = self._files.get(parts[-1].lower())
        if not candidates:
            return None
        wanted = [part.lower() for part in parts]
        scored: list[tuple[int, tuple[str, ...]]] = []
        for candidate in candidates:
            available = [part.lower() for part in candidate]
            limit = min(len(wanted), len(available))
            score = 0
            while score < limit and wanted[-1 - score] == available[-1 - score]:
                score += 1
            scored.append((score, candidate))
        best = max(score for score, _ in scored)
        winners = [candidate for score, candidate in scored if score == best]
        if len(winners) != 1:
            return None
        return self._checked_path(winners[0])

    def snippet(self, logged_path: str, line: int, radius: int) -> Snippet | None:
        if line < 1 or radius < 1:
            return None
        radius = min(radius, MAX_CONTEXT_RADIUS)
        verified = self._locate(logged_path)
        if verified is None:
            return None
        handle = self._open_verified(verified)
        if handle is None:
            return None
        first = max(1, line - radius)
        last = line + radius
        collected: list[str] = []
        reached = False
        consumed = 0
        try:
            with handle:
                for number in range(1, last + 1):
                    raw = handle.readline(MAX_SOURCE_BYTES + 1)
                    if not raw:
                        break
                    consumed += len(raw)
                    if consumed > MAX_SOURCE_BYTES:
                        return None
                    if number == line:
                        reached = True
                    if number >= first:
                        text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                        collected.append(sanitize(text, MAX_SOURCE_LINE_CHARS))
        except OSError:
            return None
        if not reached:
            return None
        display = "/".join(verified.parts)
        return Snippet(display, first, line, tuple(collected))

    def _open_verified(self, verified: _Verified) -> BinaryIO | None:
        try:
            descriptor = self._open_descriptor(verified)
        except OSError:
            return None
        with contextlib.suppress(OSError):
            if _is_checked_file(os.fstat(descriptor), verified):
                return os.fdopen(descriptor, "rb")
        os.close(descriptor)
        return None

    def _open_descriptor(self, verified: _Verified) -> int:
        if not _ANCHORED:
            return os.open(verified.path, _FILE_FLAGS | _NOFOLLOW)
        directory = os.open(self._root, os.O_RDONLY | _DIRECTORY | _NOFOLLOW)
        try:
            for part in verified.parts[:-1]:
                child = os.open(part, os.O_RDONLY | _DIRECTORY | _NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = child
            return os.open(verified.parts[-1], _FILE_FLAGS | _NOFOLLOW, dir_fd=directory)
        finally:
            os.close(directory)

    def _scan(self) -> None:
        indexed = 0
        scanned = 0
        for directory, subdirectories, files in os.walk(self._root, followlinks=False):
            scanned += 1
            if scanned > MAX_SCANNED_DIRECTORIES:
                raise SourceError(
                    f"source directory has more than {MAX_SCANNED_DIRECTORIES} sub-directories; "
                    "point --source-dir at the folder that holds your .pwn files"
                )
            subdirectories[:] = [name for name in subdirectories if name not in SKIPPED_DIRECTORIES]
            relative = Path(directory).relative_to(self._root).parts
            for name in files:
                if Path(name).suffix.lower() not in SOURCE_SUFFIXES:
                    continue
                indexed += 1
                if indexed > MAX_INDEXED_FILES:
                    raise SourceError(
                        f"source directory has more than {MAX_INDEXED_FILES} source files; "
                        "point --source-dir at a smaller folder"
                    )
                self._files.setdefault(name.lower(), []).append((*relative, name))

    def _checked_path(self, parts: tuple[str, ...]) -> _Verified | None:
        try:
            resolved = self._root.joinpath(*parts).resolve(strict=True)
            if not resolved.is_relative_to(self._root):
                return None
            info = resolved.stat()
            relative = resolved.relative_to(self._root).parts
        except (OSError, RuntimeError):
            return None
        if not _is_acceptable(info):
            return None
        return _Verified(resolved, relative, info.st_dev, info.st_ino)
