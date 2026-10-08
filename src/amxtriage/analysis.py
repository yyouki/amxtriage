from collections.abc import Collection, Sequence
from dataclasses import dataclass

from amxtriage.aggregate import MAX_GROUPS, Aggregator
from amxtriage.model import EventKind, Group
from amxtriage.parser import LogParser
from amxtriage.reader import MAX_LINE_BYTES, LineSplitter, display_name, iter_lines, open_log
from amxtriage.source import Snippet, SourceIndex


@dataclass(slots=True)
class AnalysisResult:
    sources: list[str]
    lines_read: int
    truncated_lines: int
    aggregator: Aggregator


@dataclass(slots=True)
class Report:
    sources: list[str]
    lines_read: int
    truncated_lines: int
    total_events: int
    dropped_events: int
    ignored_interrupts: int
    matching_groups: int
    groups: list[Group]
    omitted_groups: int
    known_hidden: int
    baseline_used: bool
    contexts: dict[str, Snippet]
    notes: list[str]


def analyze_logs(
    paths: Sequence[str],
    max_groups: int = MAX_GROUPS,
    max_input_bytes: int | None = None,
) -> AnalysisResult:
    aggregator = Aggregator(max_groups)
    sources: list[str] = []
    lines_read = 0
    truncated = 0
    for path in paths:
        label = display_name(path)
        sources.append(label)
        parser = LogParser()
        splitter = LineSplitter()
        with open_log(path) as stream:
            for line in iter_lines(stream, splitter, path, max_input_bytes):
                for event in parser.feed(line):
                    aggregator.add(event, label)
        for event in parser.flush():
            aggregator.add(event, label)
        lines_read += splitter.lines
        truncated += splitter.truncated
    return AnalysisResult(sources, lines_read, truncated, aggregator)


def snippet_for(group: Group, index: SourceIndex, radius: int) -> Snippet | None:
    if group.file is None:
        return None
    ranked = group.top_lines(1)
    if not ranked:
        return None
    return index.snippet(group.file, ranked[0][0], radius)


def build_report(
    result: AnalysisResult,
    *,
    top: int,
    min_count: int = 1,
    kinds: Collection[EventKind] | None = None,
    baseline: frozenset[str] | None = None,
    source_index: SourceIndex | None = None,
    context_radius: int = 0,
) -> Report:
    aggregator = result.aggregator
    matching = [
        group
        for group in aggregator.sorted_groups()
        if group.count >= min_count and (kinds is None or group.kind in kinds)
    ]
    known_hidden = 0
    if baseline is not None:
        fresh = [group for group in matching if group.signature_id not in baseline]
        known_hidden = len(matching) - len(fresh)
        matching = fresh
    displayed = matching[:top]
    contexts: dict[str, Snippet] = {}
    if source_index is not None and context_radius > 0:
        for group in displayed:
            snippet = snippet_for(group, source_index, context_radius)
            if snippet is not None:
                contexts[group.signature_id] = snippet
    notes = _notes(result, displayed, contexts, source_index, context_radius)
    return Report(
        sources=result.sources,
        lines_read=result.lines_read,
        truncated_lines=result.truncated_lines,
        total_events=aggregator.total_events,
        dropped_events=aggregator.dropped_events,
        ignored_interrupts=aggregator.ignored_interrupts,
        matching_groups=len(matching),
        groups=displayed,
        omitted_groups=len(matching) - len(displayed),
        known_hidden=known_hidden,
        baseline_used=baseline is not None,
        contexts=contexts,
        notes=notes,
    )


def _notes(
    result: AnalysisResult,
    displayed: list[Group],
    contexts: dict[str, Snippet],
    source_index: SourceIndex | None,
    context_radius: int,
) -> list[str]:
    aggregator = result.aggregator
    notes: list[str] = []
    if result.truncated_lines:
        notes.append(
            f"{result.truncated_lines:,} line(s) longer than {MAX_LINE_BYTES} bytes were truncated."
        )
    if aggregator.dropped_events:
        notes.append(
            f"Group limit of {aggregator.max_groups:,} reached: "
            f"{aggregator.dropped_events:,} event(s) with new signatures were not grouped."
        )
    if aggregator.ignored_interrupts:
        notes.append(f"{aggregator.ignored_interrupts:,} interrupt signal event(s) were ignored.")
    if displayed and all(group.function is None for group in displayed):
        notes.append(
            "No AMX backtrace with function names was found. Install crashdetect and compile "
            "your scripts with debug info (for example -d3) to get function names and file:line."
        )
    if (
        source_index is not None
        and context_radius > 0
        and not contexts
        and any(group.file is not None for group in displayed)
    ):
        notes.append(
            "No source context could be resolved: the file names in the log did not match "
            "exactly one .pwn/.inc file under --source-dir."
        )
    return notes
