import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import BinaryIO, Literal

from amxtriage.errors import InputError
from amxtriage.reader import CHUNK_SIZE, GZIP_MAGIC, PROBE_BYTES, LineSplitter, check_text_like

DEFAULT_POLL_INTERVAL = 1.0
MIN_POLL_INTERVAL = 0.1
MAX_POLL_INTERVAL = 60.0

Replacement = Literal["none", "truncated", "rotated"]


def _never_stop() -> bool:
    return False


class LogFollower:
    def __init__(
        self,
        path: str,
        *,
        from_start: bool = False,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        sleep: Callable[[float], object] = time.sleep,
        should_stop: Callable[[], bool] = _never_stop,
    ) -> None:
        self._path = Path(path)
        self._from_start = from_start
        self._poll_interval = poll_interval
        self._sleep = sleep
        self._should_stop = should_stop
        self._splitter = LineSplitter()
        self._handle: BinaryIO | None = None
        self._identity: tuple[int, int] | None = None
        self._position = 0
        self._text_checked = False

    @property
    def truncated_lines(self) -> int:
        return self._splitter.truncated

    def lines(self) -> Iterator[str | None]:
        self._start()
        try:
            while not self._should_stop():
                produced = False
                for line in self._poll():
                    produced = True
                    yield line
                if not produced:
                    yield None
                    self._sleep(self._poll_interval)
        finally:
            self.close()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def _start(self) -> None:
        if self._path.is_dir():
            raise InputError(f"'{self._path}' is a directory, expected a log file")
        handle = self._open()
        if handle.read(len(GZIP_MAGIC)) == GZIP_MAGIC:
            handle.close()
            self._handle = None
            raise InputError(
                f"'{self._path}' is compressed; 'watch' follows plain text logs only "
                "(use 'analyze' for compressed files)"
            )
        handle.seek(0, os.SEEK_END if not self._from_start else os.SEEK_SET)
        self._position = handle.tell()

    def _open(self) -> BinaryIO:
        try:
            handle = self._path.open("rb")
        except OSError as error:
            raise InputError(f"cannot open '{self._path}': {error.strerror or error}") from error
        status = os.fstat(handle.fileno())
        self._identity = (status.st_dev, status.st_ino)
        self._handle = handle
        return handle

    def _replacement(self) -> Replacement:
        try:
            status = self._path.stat()
        except OSError:
            return "none"
        if self._identity is not None and (status.st_dev, status.st_ino) != self._identity:
            return "rotated"
        if status.st_size < self._position:
            return "truncated"
        return "none"

    def _poll(self) -> Iterator[str]:
        handle = self._handle
        if handle is None:
            return
        yield from self._drain(handle)
        replacement = self._replacement()
        if replacement == "truncated":
            yield from self._splitter.finish()
            handle.seek(0)
            self._position = 0
            yield from self._drain(handle)
        elif replacement == "rotated":
            yield from self._splitter.finish()
            handle.close()
            self._position = 0
            yield from self._drain(self._open())

    def _drain(self, handle: BinaryIO) -> Iterator[str]:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                return
            self._position = handle.tell()
            if not self._text_checked:
                check_text_like(chunk[:PROBE_BYTES], str(self._path))
                self._text_checked = True
            yield from self._splitter.feed(chunk)
