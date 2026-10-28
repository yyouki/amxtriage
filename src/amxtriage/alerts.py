"""Safe, local JSONL alert events for an optional SA-MP/open.mp bridge.

This module does not connect to a game server. It emits structured records that a separately
configured, authenticated bridge can consume; source locations remain independent of templates.
"""

from __future__ import annotations

import errno
import json
import os
import stat
import string
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from pathlib import Path

from amxtriage.errors import InputError, OutputError
from amxtriage.model import Group
from amxtriage.textutil import sanitize

SCHEMA_VERSION = 1
MAX_TEMPLATE_LENGTH = 512
MAX_PREFIX_LENGTH = 80
MAX_ALERT_BYTES = 8192
DEFAULT_ALERT_PREFIX = "AMXTRIAGE"
DEFAULT_ALERT_TEMPLATE = "[{prefix}] [{severity}] {file}:{line} — {message}"
DEFAULT_ALERT_MESSAGE_TEMPLATE = "{message}"

_SEVERITY: dict[str, str] = {
    "crash": "CRITICAL",
    "runtime_error": "HIGH",
    "long_call": "MEDIUM",
}
_ALLOWED_FIELDS = frozenset(
    {"prefix", "severity", "kind", "message", "file", "line", "code", "signature", "count"}
)
_MESSAGE_TEMPLATE_FIELDS = frozenset({"severity", "kind", "message", "code", "signature", "count"})
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_NOCTTY = getattr(os, "O_NOCTTY", 0)
_BINARY = getattr(os, "O_BINARY", 0)


MAX_ALERT_COOLDOWN_SECONDS = 86400
MAX_ALERTS_PER_MINUTE = 10000
MAX_TRACKED_ALERT_SIGNATURES = 4096


class AlertThrottle:
    """Bounded in-process alert cooldown and global rate limiter.

    Repeated occurrences of one diagnostic can be re-alerted after the cooldown. A separate
    sliding one-minute limit caps bursts across distinct diagnostics. This is intentionally
    in-memory: restarting the watcher resets the policy state.
    """

    def __init__(
        self,
        *,
        cooldown_seconds: float = 300.0,
        max_per_minute: int = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 0.0 <= cooldown_seconds <= MAX_ALERT_COOLDOWN_SECONDS:
            raise InputError(
                f"alert cooldown must be between 0 and {MAX_ALERT_COOLDOWN_SECONDS} seconds"
            )
        if not 1 <= max_per_minute <= MAX_ALERTS_PER_MINUTE:
            raise InputError(
                f"alert limit must be between 1 and {MAX_ALERTS_PER_MINUTE} per minute"
            )
        self.cooldown_seconds = cooldown_seconds
        self.max_per_minute = max_per_minute
        self._clock = clock
        self._last_sent: OrderedDict[str, float] = OrderedDict()
        self._sent_times: deque[float] = deque()
        self.suppressed_count = 0

    def allow(self, group: Group) -> bool:
        """Return whether this diagnostic should be emitted to configured alert sinks."""
        now = self._clock()
        while self._sent_times and now - self._sent_times[0] >= 60.0:
            self._sent_times.popleft()

        signature = sanitize(group.signature_id, 64)
        previous = self._last_sent.get(signature)
        if (
            self.cooldown_seconds > 0
            and previous is not None
            and now - previous < self.cooldown_seconds
        ):
            self.suppressed_count += 1
            return False
        if len(self._sent_times) >= self.max_per_minute:
            self.suppressed_count += 1
            return False

        self._sent_times.append(now)
        self._last_sent[signature] = now
        self._last_sent.move_to_end(signature)
        while len(self._last_sent) > MAX_TRACKED_ALERT_SIGNATURES:
            self._last_sent.popitem(last=False)
        return True


def validate_alert_template(template: str) -> None:
    """Validate a single-line template without evaluating expressions or attribute access."""
    if len(template) > MAX_TEMPLATE_LENGTH:
        raise InputError(f"alert template exceeds {MAX_TEMPLATE_LENGTH} characters")
    if sanitize(template, MAX_TEMPLATE_LENGTH + 1) != template:
        raise InputError("alert template must be a single line without control characters")
    try:
        fields = list(string.Formatter().parse(template))
    except ValueError as error:
        raise InputError("alert template contains invalid brace syntax") from error
    for _, field_name, format_spec, conversion in fields:
        if field_name is None:
            continue
        if field_name not in _ALLOWED_FIELDS:
            raise InputError(f"unsupported alert template field: {field_name}")
        if format_spec or conversion:
            raise InputError(
                "alert template format specifications and conversions are not supported"
            )



def validate_alert_message_template(template: str) -> None:
    """Validate the in-game message body template; source path and line are protected."""
    if len(template) > MAX_TEMPLATE_LENGTH:
        raise InputError(f"alert message template exceeds {MAX_TEMPLATE_LENGTH} characters")
    if sanitize(template, MAX_TEMPLATE_LENGTH + 1) != template:
        raise InputError("alert message template must be a single line without control characters")
    try:
        fields = list(string.Formatter().parse(template))
    except ValueError as error:
        raise InputError("alert message template contains invalid brace syntax") from error
    for _, field_name, format_spec, conversion in fields:
        if field_name is None:
            continue
        if field_name not in _MESSAGE_TEMPLATE_FIELDS:
            if field_name in {"file", "line"}:
                raise InputError(
                    f"source {field_name} is protected and cannot be supplied by the message template"
                )
            raise InputError(f"unsupported alert message template field: {field_name}")
        if format_spec or conversion:
            raise InputError(
                "alert message template format specifications and conversions are not supported"
            )


def _render_alert_message(group: Group, template: str) -> str:
    validate_alert_message_template(template)
    values = {
        "severity": _SEVERITY.get(group.kind, "LOW"),
        "kind": group.kind,
        "message": sanitize(group.message or group.kind.replace("_", " "), 300),
        "code": str(group.code) if group.code is not None else "—",
        "signature": sanitize(group.signature_id, 64),
        "count": str(max(1, group.count)),
    }
    return sanitize(template.format_map(values), MAX_PAWN_MESSAGE_LENGTH)


def _clean_optional(text: str | None, limit: int = 300) -> str | None:
    if text is None:
        return None
    cleaned = sanitize(text, limit)
    return cleaned or None


def build_alert_event(
    group: Group,
    *,
    prefix: str = DEFAULT_ALERT_PREFIX,
    template: str = DEFAULT_ALERT_TEMPLATE,
) -> dict[str, object]:
    """Build a locale-independent event from a structured diagnostic group.

    The template controls displayed wording only. It cannot supply or mutate the protected
    source.file and source.line fields, which are derived from the diagnostic group.
    """
    validate_alert_template(template)
    if len(prefix) > MAX_PREFIX_LENGTH or sanitize(prefix, MAX_PREFIX_LENGTH + 1) != prefix:
        raise InputError(
            f"alert prefix must be a single line of at most {MAX_PREFIX_LENGTH} characters"
        )

    source_file = _clean_optional(group.file)
    lines = group.top_lines(1)
    source_line = lines[0][0] if lines else None
    if source_line is not None and source_line < 1:
        source_line = None

    severity = _SEVERITY.get(group.kind, "LOW")
    message = sanitize(group.message or group.kind.replace("_", " "), 300)
    values = {
        "prefix": prefix,
        "severity": severity,
        "kind": group.kind,
        "message": message,
        "file": source_file or "unknown",
        "line": str(source_line) if source_line is not None else "?",
        "code": str(group.code) if group.code is not None else "—",
        "signature": sanitize(group.signature_id, 64),
        "count": str(group.count),
    }
    summary = sanitize(template.format_map(values), 700)

    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "amxtriage",
        "event_type": "diagnostic.new",
        "event_id": sanitize(group.signature_id, 64),
        "severity": severity,
        "kind": group.kind,
        "code": group.code,
        "summary": summary,
        "source": {"file": source_file, "line": source_line},
        "presentation": {"file_color": "red", "line_color": "blue"},
        "occurrences": max(1, group.count),
        "first_seen": {
            "source": sanitize(group.first.source, 300),
            "line": group.first.line_number if group.first.line_number > 0 else None,
            "timestamp": _clean_optional(group.first.timestamp, 100),
        },
    }


def serialize_alert_event(
    group: Group,
    *,
    prefix: str = DEFAULT_ALERT_PREFIX,
    template: str = DEFAULT_ALERT_TEMPLATE,
) -> str:
    """Return one bounded UTF-8 JSONL record, including the trailing newline."""
    event = build_alert_event(group, prefix=prefix, template=template)
    record = json.dumps(event, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
    if len(record.encode("utf-8")) > MAX_ALERT_BYTES:
        raise InputError(f"serialized alert exceeds {MAX_ALERT_BYTES} bytes")
    return record


def _open_append(path: str) -> int:
    if not _NOFOLLOW and Path(path).is_symlink():
        raise OutputError(f"cannot append alerts to '{path}': refusing a symbolic link")
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | _NOFOLLOW | _NONBLOCK | _NOCTTY | _BINARY
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        if error.errno in {errno.ELOOP, getattr(errno, "EMLINK", -1)}:
            reason = "refusing a symbolic link"
        else:
            reason = str(error.strerror or error)
        raise OutputError(f"cannot append alerts to '{path}': {reason}") from error

    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise OutputError(f"cannot append alerts to '{path}': target must be a regular file")
        if info.st_nlink > 1:
            raise OutputError(
                f"cannot append alerts to '{path}': file has multiple hard links; refusing write"
            )
        if not _NOFOLLOW:
            path_info = os.stat(path, follow_symlinks=False)
            if (path_info.st_dev, path_info.st_ino) != (info.st_dev, info.st_ino):
                raise OutputError(f"cannot append alerts to '{path}': target changed while opening")
            if stat.S_ISLNK(path_info.st_mode):
                raise OutputError(f"cannot append alerts to '{path}': refusing a symbolic link")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def append_alert_event(
    path: str,
    group: Group,
    *,
    prefix: str = DEFAULT_ALERT_PREFIX,
    template: str = DEFAULT_ALERT_TEMPLATE,
) -> None:
    """Append one record without following output symlinks or writing through hard links."""
    record = serialize_alert_event(group, prefix=prefix, template=template)
    data = record.encode("utf-8")
    descriptor = _open_append(path)
    try:
        written = 0
        while written < len(data):
            try:
                count = os.write(descriptor, data[written:])
            except OSError as error:
                raise OutputError(
                    f"cannot append alerts to '{path}': {error.strerror or error}"
                ) from error
            if count <= 0:
                raise OutputError(f"cannot append alerts to '{path}': write made no progress")
            written += count
    finally:
        os.close(descriptor)


class JsonlAlertSink:
    """Optional append-only local sink; a write error disables only this sink."""

    def __init__(
        self,
        path: str,
        *,
        prefix: str = DEFAULT_ALERT_PREFIX,
        template: str = DEFAULT_ALERT_TEMPLATE,
    ) -> None:
        validate_alert_template(template)
        if len(prefix) > MAX_PREFIX_LENGTH or sanitize(prefix, MAX_PREFIX_LENGTH + 1) != prefix:
            raise InputError(
                f"alert prefix must be a single line of at most {MAX_PREFIX_LENGTH} characters"
            )
        self.path = path
        self.prefix = prefix
        self.template = template
        self.disabled = False
        self.failure_reason: str | None = None
        self.warning_emitted = False

    def emit(self, group: Group) -> bool:
        if self.disabled:
            return False
        try:
            append_alert_event(self.path, group, prefix=self.prefix, template=self.template)
        except OutputError as error:
            self.disabled = True
            self.failure_reason = sanitize(str(error), 300)
            return False
        return True


MAX_PAWN_BRIDGE_BYTES = 4096
MAX_PAWN_FILE_LENGTH = 160
MAX_PAWN_MESSAGE_LENGTH = 160


def _pawn_bridge_field(text: str, limit: int) -> str:
    """Escape record separators, percent signs and color-tag braces for the Pawn consumer.

    The bridge deliberately does not decode braces. This prevents log-derived text from
    injecting SA-MP/open.mp inline color tags such as {FF0000}.
    """
    safe = sanitize(text, limit)
    return safe.replace("%", "%25").replace("|", "%7C").replace("{", "%7B").replace("}", "%7D")


def serialize_pawn_bridge_record(
    group: Group,
    *,
    prefix: str = DEFAULT_ALERT_PREFIX,
    message_template: str = DEFAULT_ALERT_MESSAGE_TEMPLATE,
) -> str:
    """Serialize one safe, bounded record for the optional Pawn filterscript.

    Protocol: AMXTRIAGE1|severity|prefix|file|line|message|count|END\n
    Fields are pipe-separated. '%' and '|' are escaped; braces remain percent-encoded
    all the way into chat so untrusted text cannot inject inline color formatting.
    """
    if len(prefix) > MAX_PREFIX_LENGTH or sanitize(prefix, MAX_PREFIX_LENGTH + 1) != prefix:
        raise InputError(
            f"alert prefix must be a single line of at most {MAX_PREFIX_LENGTH} characters"
        )
    source_file = _clean_optional(group.file, MAX_PAWN_FILE_LENGTH) or "unknown"
    line_rows = group.top_lines(1)
    source_line = line_rows[0][0] if line_rows and line_rows[0][0] > 0 else 0
    severity = _SEVERITY.get(group.kind, "LOW")
    message = _render_alert_message(group, message_template)
    fields = (
        "AMXTRIAGE1",
        severity,
        _pawn_bridge_field(prefix, MAX_PREFIX_LENGTH),
        _pawn_bridge_field(source_file, MAX_PAWN_FILE_LENGTH),
        str(source_line),
        _pawn_bridge_field(message, MAX_PAWN_MESSAGE_LENGTH),
        str(max(1, group.count)),
        "END",
    )
    record = "|".join(fields) + "\n"
    if len(record.encode("utf-8")) > MAX_PAWN_BRIDGE_BYTES:
        raise InputError(f"Pawn bridge record exceeds {MAX_PAWN_BRIDGE_BYTES} bytes")
    return record


def append_pawn_bridge_record(
    path: str,
    group: Group,
    *,
    prefix: str = DEFAULT_ALERT_PREFIX,
    message_template: str = DEFAULT_ALERT_MESSAGE_TEMPLATE,
) -> None:
    """Append one protocol record for the Pawn filterscript using the same safe file checks."""
    data = serialize_pawn_bridge_record(
        group, prefix=prefix, message_template=message_template
    ).encode("utf-8")
    descriptor = _open_append(path)
    try:
        written = 0
        while written < len(data):
            try:
                count = os.write(descriptor, data[written:])
            except OSError as error:
                raise OutputError(
                    f"cannot append Pawn bridge alert to '{path}': {error.strerror or error}"
                ) from error
            if count <= 0:
                raise OutputError(
                    f"cannot append Pawn bridge alert to '{path}': write made no progress"
                )
            written += count
    finally:
        os.close(descriptor)


class PawnBridgeAlertSink:
    """Optional local file sink consumed by integrations/pawn/amxtriage_bridge.pwn."""

    def __init__(
        self,
        path: str,
        *,
        prefix: str = DEFAULT_ALERT_PREFIX,
        message_template: str = DEFAULT_ALERT_MESSAGE_TEMPLATE,
    ) -> None:
        if len(prefix) > MAX_PREFIX_LENGTH or sanitize(prefix, MAX_PREFIX_LENGTH + 1) != prefix:
            raise InputError(
                f"alert prefix must be a single line of at most {MAX_PREFIX_LENGTH} characters"
            )
        validate_alert_message_template(message_template)
        self.path = path
        self.prefix = prefix
        self.message_template = message_template
        self.disabled = False
        self.failure_reason: str | None = None
        self.warning_emitted = False

    def emit(self, group: Group) -> bool:
        if self.disabled:
            return False
        try:
            append_pawn_bridge_record(
                self.path,
                group,
                prefix=self.prefix,
                message_template=self.message_template,
            )
        except OutputError as error:
            self.disabled = True
            self.failure_reason = sanitize(str(error), 300)
            return False
        return True
