import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import NamedTuple

from amxtriage.model import Event, EventKind, Frame, NativeFrame

MAX_TAGS = 3
MAX_FRAMES = 48
MAX_NATIVE_FRAMES = 16
MAX_DETAILS = 4
MAX_NAME_DETAILS = 64
QUIET_LINE_TOLERANCE = 2
NAME_DETAIL_CODES = frozenset({10, 19})

_TIMESTAMP = re.compile(r"\[(\d[^\[\]]{0,63})\] ?")
_TAG = re.compile(r"\[([A-Za-z][\w\-]{0,31})\] ?")
_QUICK = re.compile(
    r"Run time error|Server crashed|Long callback execution|Server received interrupt"
)
_RUNTIME_ERROR = re.compile(
    r"(?:Script\[(?P<script>[^\]]{1,260})\]: )?"
    r'Run time error (?P<code>\d{1,3}): "(?P<message>[^"]{0,200})"'
)
_CRASH = re.compile(
    r"Server crashed (?:while executing (?P<script>.{1,260})|due to an unknown error)"
)
_INTERRUPT = re.compile(
    r"Server received interrupt signal(?: while executing (?P<script>.{1,260}))?"
)
_LONG_CALL_PREFIX = "Long callback execution detected"
_FRAME_INDEX = re.compile(r"#(\d{1,5}) ")
_ADDRESS_IN = re.compile(r"[0-9A-Fa-f]{6,16} in ")
_NATIVE_FRAME = re.compile(r"native (?P<name>\S{1,128}) \(\)(?: (?:in|from) (?P<module>.{1,260}))?")
_LOCATION = re.compile(r"(?P<file>.{1,500}):(?P<line>\d{1,9})")
_NAME_DETAIL = re.compile(r"[A-Za-z_@][\w@.]{0,127}")
_DETAIL_PATTERNS = (
    re.compile(
        r"Attempted to read/write array element at (?:negative )?index -?\d+"
        r"(?: in array of size \d+)?"
    ),
    re.compile(r"Accessing element at (?:negative )?index -?\d+(?: past array upper bound -?\d+)?"),
    re.compile(
        r"Stack pointer \(STK\) is 0x[0-9A-Fa-f]+, "
        r"(?:heap pointer \(HEA\)|stack top \(STP\)) is 0x[0-9A-Fa-f]+"
    ),
    re.compile(r"Heap pointer \(HEA\) is 0x[0-9A-Fa-f]+, heap bottom \(HLW\) is 0x[0-9A-Fa-f]+"),
    re.compile(r"Unknown opcode 0x[0-9A-Fa-f]+ at address 0x[0-9A-Fa-f]+"),
)


class Prefix(NamedTuple):
    timestamp: str | None
    tags: tuple[str, ...]
    body: str


class _Header(NamedTuple):
    kind: EventKind
    code: int | None
    message: str | None
    script: str | None


def split_prefix(line: str) -> Prefix:
    position = 0
    timestamp: str | None = None
    match = _TIMESTAMP.match(line)
    if match is not None:
        timestamp = match.group(1)
        position = match.end()
    tags: list[str] = []
    while len(tags) < MAX_TAGS:
        tag_match = _TAG.match(line, position)
        if tag_match is None:
            break
        tags.append(tag_match.group(1).lower())
        position = tag_match.end()
    return Prefix(timestamp, tuple(tags), line[position:])


def _parse_header(body: str) -> _Header | None:
    match = _RUNTIME_ERROR.match(body)
    if match is not None:
        return _Header("runtime_error", int(match["code"]), match["message"], match["script"])
    if body.startswith(_LONG_CALL_PREFIX):
        return _Header("long_call", None, None, None)
    text = body.rstrip()
    crash = _CRASH.fullmatch(text)
    if crash is not None:
        return _Header("crash", None, None, crash["script"])
    interrupt = _INTERRUPT.fullmatch(text)
    if interrupt is not None:
        return _Header("interrupt", None, None, interrupt["script"])
    return None


def _function_name(raw: str) -> str:
    name = raw.rsplit(":", 1)[-1] if ":" in raw else raw
    return name[:128] or "??"


def _parse_amx_frame(index: int, rest: str) -> Frame | None:
    public = rest.startswith("public ")
    if public:
        rest = rest[len("public ") :]
    split = rest.find(" (")
    if split <= 0:
        return None
    function = _function_name(rest[:split])
    tail = rest[split + 2 :]
    file: str | None = None
    line: int | None = None
    module: str | None = None
    marker = tail.rfind(" at ")
    if marker != -1:
        location = _LOCATION.fullmatch(tail[marker + len(" at ") :])
        if location is not None:
            file = location["file"]
            line = int(location["line"])
            tail = tail[:marker]
    if file is None:
        marker = tail.rfind(") in ")
        if marker != -1:
            module = tail[marker + len(") in ") :].strip() or None
            tail = tail[: marker + 1]
    close = tail.rfind(")")
    if close == -1:
        return None
    if file is not None and file.startswith("<unknown"):
        file = None
    return Frame(index, "amx", function, public, file, line, module, tail[:close])


def parse_frame(text: str) -> Frame | None:
    index_match = _FRAME_INDEX.match(text)
    if index_match is None:
        return None
    index = int(index_match.group(1))
    rest = text[index_match.end() :]
    native = _NATIVE_FRAME.fullmatch(rest)
    if native is not None:
        return Frame(index, "native", native["name"], False, None, None, native["module"], None)
    address = _ADDRESS_IN.match(rest)
    if address is None:
        return None
    return _parse_amx_frame(index, rest[address.end() :])


def parse_native_frame(text: str) -> NativeFrame | None:
    index_match = _FRAME_INDEX.match(text)
    if index_match is None:
        return None
    rest = text[index_match.end() :]
    address = _ADDRESS_IN.match(rest)
    if address is None:
        return None
    rest = rest[address.end() :]
    marker = rest.find(" ()")
    index = int(index_match.group(1))
    if marker == -1:
        return NativeFrame(index, rest[:128], None)
    tail = rest[marker + len(" ()") :]
    module = tail[len(" in ") :].strip() if tail.startswith(" in ") else None
    return NativeFrame(index, rest[:marker][:128], module or None)


def _detail_text(code: int | None, body: str) -> str | None:
    if len(body) < 2 or body[0] != " " or body[1] == " ":
        return None
    text = body.strip()
    if any(pattern.fullmatch(text) for pattern in _DETAIL_PATTERNS):
        return text
    if code in NAME_DETAIL_CODES and _NAME_DETAIL.fullmatch(text):
        return text
    return None


@dataclass(slots=True)
class _Block:
    kind: EventKind
    line_number: int
    timestamp: str | None
    code: int | None
    message: str | None
    script: str | None
    section: str = "header"
    quiet: int = 0
    details: list[str] = field(default_factory=list)
    frames: list[Frame] = field(default_factory=list)
    native_frames: list[NativeFrame] = field(default_factory=list)

    def to_event(self) -> Event:
        return Event(
            kind=self.kind,
            line_number=self.line_number,
            timestamp=self.timestamp,
            code=self.code,
            message=self.message,
            script=self.script,
            details=tuple(self.details),
            frames=tuple(self.frames),
            native_frames=tuple(self.native_frames),
        )


class LogParser:
    def __init__(self) -> None:
        self._block: _Block | None = None
        self._line_number = 0

    @property
    def line_number(self) -> int:
        return self._line_number

    @property
    def has_open_block(self) -> bool:
        return self._block is not None

    def feed(self, line: str) -> list[Event]:
        self._line_number += 1
        if self._block is None and _QUICK.search(line) is None:
            return []
        prefix = split_prefix(line)
        header = _parse_header(prefix.body)
        if header is not None:
            return self._handle_header(header, prefix.timestamp)
        block = self._block
        if block is None:
            return []
        if self._absorb(block, prefix.body):
            block.quiet = 0
            return []
        block.quiet += 1
        if block.quiet > QUIET_LINE_TOLERANCE:
            return [self._close()]
        return []

    def flush(self) -> list[Event]:
        if self._block is None:
            return []
        return [self._close()]

    def _close(self) -> Event:
        block = self._block
        if block is None:
            raise RuntimeError("no open block to close")
        self._block = None
        return block.to_event()

    def _handle_header(self, header: _Header, timestamp: str | None) -> list[Event]:
        events: list[Event] = []
        block = self._block
        if header.kind == "runtime_error" and header.script is not None:
            if (
                block is not None
                and block.kind == "runtime_error"
                and block.script is None
                and block.code == header.code
            ):
                block.script = header.script
                events.append(self._close())
                return events
            if block is not None:
                events.append(self._close())
            events.append(
                Event(
                    kind="runtime_error",
                    line_number=self._line_number,
                    timestamp=timestamp,
                    code=header.code,
                    message=header.message,
                    script=header.script,
                    details=(),
                    frames=(),
                    native_frames=(),
                )
            )
            return events
        if block is not None:
            events.append(self._close())
        self._block = _Block(
            kind=header.kind,
            line_number=self._line_number,
            timestamp=timestamp,
            code=header.code,
            message=header.message,
            script=header.script,
        )
        return events

    @staticmethod
    def _absorb(block: _Block, body: str) -> bool:
        text = body.strip()
        if text == "AMX backtrace:":
            block.section = "amx"
            return True
        if text == "Native backtrace:":
            block.section = "native"
            return True
        if block.section == "amx":
            if not text.startswith("#"):
                return False
            frame = parse_frame(text)
            if frame is not None and len(block.frames) < MAX_FRAMES:
                block.frames.append(frame)
            return True
        if block.section == "native":
            if not text.startswith("#"):
                return False
            native = parse_native_frame(text)
            if native is not None and len(block.native_frames) < MAX_NATIVE_FRAMES:
                block.native_frames.append(native)
            return True
        if block.kind != "runtime_error":
            return False
        detail = _detail_text(block.code, body)
        if detail is None:
            return False
        limit = MAX_NAME_DETAILS if block.code in NAME_DETAIL_CODES else MAX_DETAILS
        if len(block.details) < limit:
            block.details.append(detail)
        return True


def parse_lines(lines: Iterable[str]) -> Iterator[Event]:
    parser = LogParser()
    for line in lines:
        yield from parser.feed(line)
    yield from parser.flush()
