import contextlib
import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

from amxtriage import __version__
from amxtriage.aggregate import SIGNATURE_ID_LENGTH
from amxtriage.errors import BaselineError
from amxtriage.model import Group
from amxtriage.textutil import sanitize

SCHEMA_VERSION = 1
MAX_BASELINE_BYTES = 10 * 1024 * 1024

_HEX_DIGITS = frozenset("0123456789abcdef")


def save_baseline(path: str, groups: Iterable[Group]) -> int:
    entries = [
        {
            "id": group.signature_id,
            "kind": group.kind,
            "code": group.code,
            "function": sanitize(group.function, 128) if group.function is not None else None,
            "count": group.count,
        }
        for group in groups
    ]
    payload = {
        "tool": "amxtriage",
        "schema_version": SCHEMA_VERSION,
        "tool_version": __version__,
        "signatures": entries,
    }
    text = json.dumps(payload, indent=2) + "\n"
    target = Path(path)
    temp_name: str | None = None
    try:
        descriptor, temp_name = tempfile.mkstemp(
            dir=target.parent, prefix=".amxtriage-", suffix=".tmp"
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(temp_name, 0o644)
        os.replace(temp_name, target)
    except OSError as error:
        if temp_name is not None:
            with contextlib.suppress(OSError):
                os.unlink(temp_name)
        raise BaselineError(f"cannot write baseline '{path}': {error.strerror or error}") from error
    return len(entries)


def _validated_ids(data: object, path: str) -> list[str]:
    if not isinstance(data, dict) or data.get("tool") != "amxtriage":
        raise BaselineError(f"'{path}' is not an amxtriage baseline file")
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise BaselineError(
            f"'{path}' has unsupported schema_version {version!r}; expected {SCHEMA_VERSION}"
        )
    signatures = data.get("signatures")
    if not isinstance(signatures, list):
        raise BaselineError(f"'{path}' has no valid 'signatures' list")
    identifiers: list[str] = []
    for entry in signatures:
        identifier = entry.get("id") if isinstance(entry, dict) else None
        if (
            not isinstance(identifier, str)
            or len(identifier) != SIGNATURE_ID_LENGTH
            or not set(identifier) <= _HEX_DIGITS
        ):
            raise BaselineError(f"'{path}' contains an invalid signature id")
        identifiers.append(identifier)
    return identifiers


def load_baseline(path: str) -> frozenset[str]:
    target = Path(path)
    try:
        size = target.stat().st_size
    except FileNotFoundError as error:
        raise BaselineError(f"baseline file '{path}' does not exist") from error
    except OSError as error:
        raise BaselineError(f"cannot read baseline '{path}': {error.strerror or error}") from error
    if size > MAX_BASELINE_BYTES:
        raise BaselineError(f"baseline file '{path}' is larger than {MAX_BASELINE_BYTES} bytes")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise BaselineError(f"cannot read baseline '{path}': {error}") from error
    return frozenset(_validated_ids(data, path))
