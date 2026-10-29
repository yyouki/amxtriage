import errno
import os
import stat

from amxtriage.errors import OutputError

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_LINK_ERRORS = frozenset(
    code
    for code in (errno.ELOOP, getattr(errno, "EMLINK", None), getattr(errno, "EFTYPE", None))
    if code is not None
)


def _open_failure(path: str, error: OSError) -> str:
    if error.errno in _LINK_ERRORS and os.path.islink(path):
        return "it is a symbolic link; refusing to write through it"
    return str(error.strerror or error)


def _prepare(descriptor: int, path: str) -> None:
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode):
        return
    if info.st_nlink > 1:
        raise OutputError(
            f"cannot write '{path}': the file has {info.st_nlink} hard links and writing "
            "would change all of them; remove the file first"
        )
    os.ftruncate(descriptor, 0)


def write_text_file(path: str, text: str) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | _NOFOLLOW
        | getattr(os, "O_NOCTTY", 0)
        | getattr(os, "O_BINARY", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o666)
    except OSError as error:
        raise OutputError(f"cannot write '{path}': {_open_failure(path, error)}") from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            _prepare(descriptor, path)
            handle.write(text)
    except OSError as error:
        raise OutputError(f"cannot write '{path}': {error.strerror or error}") from error
