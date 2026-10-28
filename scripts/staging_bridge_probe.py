#!/usr/bin/env python3
"""Append a clearly labeled synthetic alert for manual bridge verification on staging."""

from __future__ import annotations

import argparse
import os
import stat
import sys
from collections.abc import Sequence
from pathlib import Path

PROBE_RECORD = (
    "AMXTRIAGE1|LOW|STAGING-PROBE|staging/bridge_probe.pwn|4242|"
    "SYNTHETIC TEST ONLY - verify admin-only delivery and red/blue location colors|1|END\n"
)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_NOCTTY = getattr(os, "O_NOCTTY", 0)


class ProbeError(RuntimeError):
    """Raised when the target cannot be safely used for a staging probe."""


def _open_append(path: Path) -> int:
    """Open an existing regular file or create it privately without following links."""
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | _NOFOLLOW | _NONBLOCK | _NOCTTY
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        raise ProbeError(f"cannot open alert file {str(path)!r}: {error.strerror or error}") from error

    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ProbeError(f"alert target {str(path)!r} must be a regular file")
        if info.st_nlink > 1:
            raise ProbeError(f"alert target {str(path)!r} has multiple hard links; refusing write")
        if not _NOFOLLOW:
            path_info = os.stat(path, follow_symlinks=False)
            if stat.S_ISLNK(path_info.st_mode):
                raise ProbeError(f"alert target {str(path)!r} is a symbolic link")
            if (path_info.st_dev, path_info.st_ino) != (info.st_dev, info.st_ino):
                raise ProbeError(f"alert target {str(path)!r} changed while opening")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def append_probe(path: str | Path) -> None:
    """Append one bounded probe record; never truncate or replace the alert file."""
    target = Path(path)
    descriptor = _open_append(target)
    try:
        data = PROBE_RECORD.encode("ascii")
        written = os.write(descriptor, data)
        if written != len(data):
            raise ProbeError(
                f"short write to {str(target)!r}: wrote {written} of {len(data)} bytes; "
                "stop the watcher and inspect the final line before retrying"
            )
        os.fsync(descriptor)
    except OSError as error:
        raise ProbeError(
            f"cannot append staging probe to {str(target)!r}: {error.strerror or error}"
        ) from error
    finally:
        os.close(descriptor)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare or append one synthetic AMXTRIAGE1 record for manual verification on a "
            "SA-MP/open.mp staging server. It does not connect to a server or verify chat delivery."
        )
    )
    parser.add_argument(
        "alert_file",
        type=Path,
        help="the exact local file passed to --alert-pawn-file",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="append one low-severity synthetic record (otherwise only show a dry run)",
    )
    parser.add_argument(
        "--confirm-staging",
        action="store_true",
        help="explicitly confirm that the target is a staging-server alert file",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.send and not args.confirm_staging:
        print(
            "error: --send requires --confirm-staging; do not use this probe on production",
            file=sys.stderr,
        )
        return 2

    if not args.send:
        print(f"DRY RUN: would append one synthetic record to {str(args.alert_file)!r}.")
        print("No file was opened or changed. Use --send --confirm-staging on a staging server.")
        return 0

    try:
        append_probe(args.alert_file)
    except ProbeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(f"Appended one synthetic staging record to {str(args.alert_file)!r}.")
    print("Expected: a LOW [STAGING-PROBE] message for RCON admins only.")
    print("Verify red source path, blue line 4242, non-admin invisibility, and server logs manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
