import hashlib
from typing import NamedTuple

from amxtriage.model import Event, EventKind, Group, Occurrence
from amxtriage.parser import NAME_DETAIL_CODES
from amxtriage.textutil import basename

SIGNATURE_VERSION = "v1"
SIGNATURE_ID_LENGTH = 12
MAX_GROUPS = 5000
MAX_LINE_BUCKETS = 64

_KIND_ORDER: dict[EventKind, int] = {
    "crash": 0,
    "runtime_error": 1,
    "long_call": 2,
    "interrupt": 3,
}


def canonical_signature(event: Event) -> str:
    frame = event.primary_frame
    function = ""
    location = ""
    script = ""
    extra = ""
    if frame is not None:
        function = frame.function
        location = basename(frame.file) if frame.file else ""
    else:
        if event.script:
            script = basename(event.script)
        if event.kind == "crash" and event.native_frames:
            first = event.native_frames[0]
            module = basename(first.module) if first.module else ""
            extra = f"{first.callee}@{module}"
        elif event.code in NAME_DETAIL_CODES and event.details:
            extra = ",".join(sorted(event.details))
    code = "" if event.code is None else str(event.code)
    return "|".join((SIGNATURE_VERSION, event.kind, code, function, location, script, extra))


def signature_id(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:SIGNATURE_ID_LENGTH]


class AddResult(NamedTuple):
    group: Group | None
    created: bool


class Aggregator:
    def __init__(self, max_groups: int = MAX_GROUPS) -> None:
        self._groups: dict[str, Group] = {}
        self.max_groups = max_groups
        self.total_events = 0
        self.dropped_events = 0
        self.ignored_interrupts = 0

    def __len__(self) -> int:
        return len(self._groups)

    def add(self, event: Event, source: str) -> AddResult:
        if event.kind == "interrupt":
            self.ignored_interrupts += 1
            return AddResult(None, False)
        self.total_events += 1
        canonical = canonical_signature(event)
        identifier = signature_id(canonical)
        occurrence = Occurrence(source, event.line_number, event.timestamp)
        group = self._groups.get(identifier)
        created = group is None
        if group is None:
            if len(self._groups) >= self.max_groups:
                self.dropped_events += 1
                return AddResult(None, False)
            frame = event.primary_frame
            group = Group(
                signature_id=identifier,
                canonical=canonical,
                kind=event.kind,
                code=event.code,
                message=event.message,
                script=event.script,
                function=frame.function if frame is not None else None,
                file=frame.file if frame is not None else None,
                count=1,
                first=occurrence,
                last=occurrence,
                sample=event,
            )
            self._groups[identifier] = group
        else:
            group.count += 1
            group.last = occurrence
        self._record_line(group, event)
        return AddResult(group, created)

    def sorted_groups(self) -> list[Group]:
        return sorted(
            self._groups.values(), key=lambda group: (_KIND_ORDER[group.kind], -group.count)
        )

    @staticmethod
    def _record_line(group: Group, event: Event) -> None:
        frame = event.primary_frame
        if frame is None or frame.line is None:
            return
        counts = group.line_counts
        if frame.line in counts:
            counts[frame.line] += 1
        elif len(counts) < MAX_LINE_BUCKETS:
            counts[frame.line] = 1
