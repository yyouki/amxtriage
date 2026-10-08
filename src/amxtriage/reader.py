import codecs
import gzip
import sys
import zlib
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Protocol

from amxtriage.errors import InputError

STDIN_NAME = "-"
CHUNK_SIZE = 1 << 20
MAX_LINE_BYTES = 8192
PROBE_BYTES = 4096
GZIP_MAGIC = b"\x1f\x8b"


class ByteReader(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...


def decode_line(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").rstrip("\r")


class LineSplitter:
    def __init__(self, max_line_bytes: int = MAX_LINE_BYTES) -> None:
        self._max = max_line_bytes
        self._partial = bytearray()
        self._overlong = False
        self._at_start = True
        self.lines = 0
        self.truncated = 0

    def feed(self, data: bytes) -> list[str]:
        if self._at_start and data:
            self._at_start = False
            if data.startswith(codecs.BOM_UTF8):
                data = data[len(codecs.BOM_UTF8) :]
        pieces = data.split(b"\n")
        last = len(pieces) - 1
        lines: list[str] = []
        for index, piece in enumerate(pieces):
            if index == last:
                self._extend(piece)
            elif self._partial or self._overlong:
                self._extend(piece)
                lines.append(self._take())
            else:
                if len(piece) > self._max:
                    self.truncated += 1
                    piece = piece[: self._max]
                lines.append(decode_line(piece))
        self.lines += len(lines)
        return lines

    def finish(self) -> list[str]:
        if not self._partial and not self._overlong:
            return []
        self.lines += 1
        return [self._take()]

    def _extend(self, piece: bytes) -> None:
        if self._overlong or not piece:
            return
        self._partial += piece
        if len(self._partial) > self._max:
            del self._partial[self._max :]
            self._overlong = True
            self.truncated += 1

    def _take(self) -> str:
        text = decode_line(bytes(self._partial))
        self._partial.clear()
        self._overlong = False
        return text


def display_name(path: str) -> str:
    if path == STDIN_NAME:
        return "<stdin>"
    return Path(path).name or path


def check_text_like(head: bytes, label: str) -> None:
    if head.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        raise InputError(f"'{label}' is UTF-16 encoded; re-save it as UTF-8 and try again")
    if b"\x00" in head:
        raise InputError(f"'{label}' looks like a binary file, not a text log")


@contextmanager
def open_log(path: str) -> Iterator[ByteReader]:
    if path == STDIN_NAME:
        yield sys.stdin.buffer
        return
    target = Path(path)
    if target.is_dir():
        raise InputError(f"'{path}' is a directory, expected a log file")
    with ExitStack() as stack:
        try:
            raw = stack.enter_context(target.open("rb"))
            magic = raw.read(len(GZIP_MAGIC))
            raw.seek(0)
        except OSError as error:
            raise InputError(f"cannot open '{path}': {error.strerror or error}") from error
        if magic == GZIP_MAGIC:
            yield stack.enter_context(gzip.GzipFile(fileobj=raw))
        else:
            yield raw


def size_limit_message(label: str, limit: int) -> str:
    return (
        f"'{label}' is larger than the limit of {limit} bytes (counted after decompression); "
        "raise it with --max-input-bytes, or use 0 for no limit"
    )


def iter_lines(
    stream: ByteReader, splitter: LineSplitter, label: str, max_bytes: int | None = None
) -> Iterator[str]:
    first_chunk = True
    total = 0
    try:
        while True:
            size = CHUNK_SIZE if max_bytes is None else min(CHUNK_SIZE, max_bytes - total + 1)
            chunk = stream.read(size)
            if not chunk:
                break
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise InputError(size_limit_message(label, max_bytes))
            if first_chunk:
                check_text_like(chunk[:PROBE_BYTES], label)
                first_chunk = False
            yield from splitter.feed(chunk)
        yield from splitter.finish()
    except (OSError, EOFError, zlib.error) as error:
        raise InputError(f"failed while reading '{label}': {error}") from error
