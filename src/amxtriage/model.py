from dataclasses import dataclass, field
from typing import Literal

EventKind = Literal["runtime_error", "crash", "long_call", "interrupt"]
FrameKind = Literal["amx", "native"]

REPORTED_KINDS: tuple[EventKind, ...] = ("runtime_error", "crash", "long_call")

ARGS_DISPLAY_LIMIT = 400
MAX_STORED_ARGS = ARGS_DISPLAY_LIMIT + 1


@dataclass(frozen=True, slots=True)
class Frame:
    index: int
    kind: FrameKind
    function: str
    public: bool
    file: str | None
    line: int | None
    module: str | None
    args: str | None


@dataclass(frozen=True, slots=True)
class NativeFrame:
    index: int
    callee: str
    module: str | None


@dataclass(frozen=True, slots=True)
class Event:
    kind: EventKind
    line_number: int
    timestamp: str | None
    code: int | None
    message: str | None
    script: str | None
    details: tuple[str, ...]
    frames: tuple[Frame, ...]
    native_frames: tuple[NativeFrame, ...]

    @property
    def primary_frame(self) -> Frame | None:
        for frame in self.frames:
            if frame.kind == "amx" and frame.function != "??":
                return frame
        return None


@dataclass(frozen=True, slots=True)
class Occurrence:
    source: str
    line_number: int
    timestamp: str | None


@dataclass(slots=True)
class Group:
    signature_id: str
    canonical: str
    kind: EventKind
    code: int | None
    message: str | None
    script: str | None
    function: str | None
    file: str | None
    count: int
    first: Occurrence
    last: Occurrence
    sample: Event
    line_counts: dict[int, int] = field(default_factory=dict)

    def top_lines(self, limit: int) -> list[tuple[int, int]]:
        ranked = sorted(self.line_counts.items(), key=lambda item: (-item[1], item[0]))
        return ranked[:limit]
