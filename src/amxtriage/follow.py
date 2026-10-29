import os
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import BinaryIO, Literal

from amxtriage.errors import InputError
from amxtriage.model import Event
from amxtriage.parser import LogParser
from amxtriage.reader import CHUNK_SIZE, GZIP_MAGIC, PROBE_BYTES, LineSplitter, check_text_like

DEFAULT_POLL_INTERVAL = 1.0
MIN_POLL_INTERVAL = 0.1
MAX_POLL_INTERVAL = 60.0
QUIET_POLLS_BEFORE_FLUSH = 2
SLEEP_SLICE_SECONDS = 0.25

Replacement = Literal["none", "truncated", "rotated"]


def _never_stop() -> bool:
    return False


def interruptible_sleep(
    stop: threading.Event,
    slice_seconds: float = SLEEP_SLICE_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> Callable[[float], bool]:
    def sleep(seconds: float) -> bool:
        deadline = clock() + seconds
        while not stop.is_set():
            remaining = deadline - clock()
            if remaining <= 0:
                break
            stop.wait(min(slice_seconds, remaining))
        return stop.is_set()

    return sleep


class FollowParser:
    def __init__(self, quiet_polls: int = QUIET_POLLS_BEFORE_FLUSH) -> None:
        self._parser = LogParser()
        self._quiet_polls = quiet_polls
        self._quiet = 0

    @property
    def line_number(self) -> int:
        return self._parser.line_number

    def feed(self, line: str) -> list[Event]:
        self._quiet = 0
        return self._parser.feed(line)

    def idle(self) -> list[Event]:
        self._quiet += 1
        if self._quiet < self._quiet_polls:
            return []
        return self._parser.flush()

    def finish(self) -> list[Event]:
        return self._parser.flush()


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

    def _open_raw(self) -> BinaryIO:
        if os.name != "nt" or not isinstance(self._path, Path):
            return self._path.open("rb")

        # Share-delete is required for Windows log rotation to rename an open file.
        import ctypes
        import importlib
        from ctypes import wintypes

        msvcrt = importlib.import_module("msvcrt")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        create_file.restype = wintypes.HANDLE
        sharing = 0x00000001 | 0x00000002 | 0x00000004
        handle = create_file(str(self._path), 0x80000000, sharing, None, 3, 0x00000080, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            descriptor = msvcrt.open_osfhandle(
                int(handle), os.O_RDONLY | getattr(os, "O_BINARY", 0)
            )
        except OSError:
            kernel32.CloseHandle(handle)
            raise
        return os.fdopen(descriptor, "rb")

    def _open(self) -> BinaryIO:
        try:
            return self._adopt(self._open_raw())
        except OSError as error:
            raise InputError(f"cannot open '{self._path}': {error.strerror or error}") from error

    def _adopt(self, handle: BinaryIO) -> BinaryIO:
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
            try:
                fresh = self._open_raw()
            except FileNotFoundError:
                return
            except OSError as error:
                raise InputError(
                    f"cannot open '{self._path}': {error.strerror or error}"
                ) from error
            yield from self._drain(handle)
            yield from self._splitter.finish()
            handle.close()
            self._position = 0
            yield from self._drain(self._adopt(fresh))

    def _drain(self, handle: BinaryIO) -> Iterator[str]:
        while not self._should_stop():
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                return
            self._position = handle.tell()
            if not self._text_checked:
                check_text_like(chunk[:PROBE_BYTES], str(self._path))
                self._text_checked = True
            yield from self._splitter.feed(chunk)
