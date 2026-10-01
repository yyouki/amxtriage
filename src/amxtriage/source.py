import os
import re
from dataclasses import dataclass
from pathlib import Path

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


@dataclass(frozen=True, slots=True)
class Snippet:
    path: str
    first_line: int
    target_line: int
    lines: tuple[str, ...]


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
    def file_count(self) -> int:
        return sum(len(paths) for paths in self._files.values())

    def find(self, logged_path: str) -> Path | None:
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
        path = self.find(logged_path)
        if path is None:
            return None
        first = max(1, line - radius)
        last = line + radius
        collected: list[str] = []
        reached = False
        try:
            with path.open("rb") as handle:
                for number, raw in enumerate(handle, start=1):
                    if number > last:
                        break
                    if number == line:
                        reached = True
                    if number >= first:
                        text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                        collected.append(sanitize(text, MAX_SOURCE_LINE_CHARS))
        except OSError:
            return None
        if not reached:
            return None
        display = "/".join(path.relative_to(self._root).parts)
        return Snippet(display, first, line, tuple(collected))

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

    def _checked_path(self, parts: tuple[str, ...]) -> Path | None:
        try:
            resolved = self._root.joinpath(*parts).resolve(strict=True)
            if not resolved.is_relative_to(self._root) or not resolved.is_file():
                return None
            if resolved.stat().st_size > MAX_SOURCE_BYTES:
                return None
        except (OSError, RuntimeError):
            return None
        return resolved
