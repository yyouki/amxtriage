import json

from amxtriage import __version__
from amxtriage.amxerrors import AmxError, all_errors, causes_for
from amxtriage.analysis import Report
from amxtriage.model import ARGS_DISPLAY_LIMIT, Frame, Group, NativeFrame, Occurrence
from amxtriage.source import Snippet
from amxtriage.textutil import inline_code, sanitize

JSON_SCHEMA_VERSION = 1
MAX_TRACE_FRAMES = 12
MAX_NATIVE_TRACE_FRAMES = 6
MAX_DETAIL_LINES = 10
MAX_JSON_LINES = 10
PAD = "    "

FORMATS = ("text", "markdown", "json")


def _count(value: int) -> str:
    return f"{value:,}"


def group_title(group: Group) -> str:
    if group.kind == "crash":
        script = f" while executing {sanitize(group.script, 200)}" if group.script else ""
        return f"CRASH{script}"
    if group.kind == "long_call":
        return "LONG CALLBACK (hang or performance issue)"
    message = sanitize(group.message or "unknown error", 200)
    return f"RUNTIME ERROR {group.code}: {message}"


def format_frame(frame: Frame, show_args: bool) -> str:
    prefix = "native " if frame.kind == "native" else ("public " if frame.public else "")
    text = f"#{frame.index} {prefix}{sanitize(frame.function, 128)}"
    if show_args and frame.args is not None:
        text += f"({sanitize(frame.args, ARGS_DISPLAY_LIMIT)})"
    if frame.file is not None and frame.line is not None:
        text += f"  {sanitize(frame.file, 200)}:{frame.line}"
    elif frame.module is not None:
        text += f"  ({sanitize(frame.module, 120)})"
    return text


def format_native_frame(frame: NativeFrame) -> str:
    text = f"#{frame.index} {sanitize(frame.callee, 128)}"
    if frame.module is not None:
        text += f"  ({sanitize(frame.module, 120)})"
    return text


def format_occurrence(occurrence: Occurrence) -> str:
    stamp = f" [{sanitize(occurrence.timestamp, 64)}]" if occurrence.timestamp else ""
    return f"{sanitize(occurrence.source, 120)}:{occurrence.line_number}{stamp}"


def format_seen(group: Group) -> str:
    if group.count == 1:
        return f"at {format_occurrence(group.first)}"
    return f"first {format_occurrence(group.first)}, last {format_occurrence(group.last)}"


def format_where(group: Group) -> str | None:
    if group.function is None:
        return None
    text = sanitize(group.function, 128)
    ranked = group.top_lines(3)
    if group.file is None or not ranked:
        return f"{text}  (no file:line information; compile the script with -d3)"
    show_counts = len(group.line_counts) > 1
    pieces: list[str] = []
    for position, (line, count) in enumerate(ranked):
        label = f"{sanitize(group.file, 200)}:{line}" if position == 0 else f":{line}"
        pieces.append(f"{label} (x{_count(count)})" if show_counts else label)
    return f"{text}  {', '.join(pieces)}"


def _snippet_lines(snippet: Snippet) -> list[str]:
    width = len(str(snippet.first_line + len(snippet.lines) - 1))
    rows: list[str] = []
    for offset, text in enumerate(snippet.lines):
        number = snippet.first_line + offset
        marker = ">" if number == snippet.target_line else " "
        rows.append(f"{marker} {number:>{width}} | {text}")
    return rows


def _hint_lines(group: Group) -> list[str]:
    causes = causes_for(group.kind, group.code)
    if not causes:
        return []
    text = causes[0]
    if group.kind == "runtime_error" and group.code is not None and len(causes) > 1:
        text += f" (more: amxtriage explain {group.code})"
    return [text]


def render_group_text(
    group: Group,
    *,
    show_args: bool = False,
    snippet: Snippet | None = None,
    new: bool = False,
    index: int | None = None,
) -> list[str]:
    label = f"[{index}] " if index is not None else ""
    badge = "NEW  " if new else ""
    lines = [
        f"{label}{badge}{group_title(group)}   x{_count(group.count)}   id={group.signature_id}"
    ]
    where = format_where(group)
    if where is not None:
        lines.append(f"{PAD}where  : {where}")
    if group.kind == "runtime_error" and group.script:
        lines.append(f"{PAD}script : {sanitize(group.script, 200)}")
    lines.append(f"{PAD}seen   : {format_seen(group)}")
    details = group.sample.details
    lines.extend(f"{PAD}detail : {sanitize(detail, 200)}" for detail in details[:MAX_DETAIL_LINES])
    if len(details) > MAX_DETAIL_LINES:
        lines.append(f"{PAD}detail : ... {len(details) - MAX_DETAIL_LINES} more")
    frames = group.sample.frames
    if frames:
        lines.append(f"{PAD}trace  :")
        lines.extend(
            f"{PAD}  {format_frame(frame, show_args)}" for frame in frames[:MAX_TRACE_FRAMES]
        )
        if len(frames) > MAX_TRACE_FRAMES:
            lines.append(f"{PAD}  ... {len(frames) - MAX_TRACE_FRAMES} more frame(s)")
    native_frames = group.sample.native_frames
    if group.kind == "crash" and native_frames:
        lines.append(f"{PAD}native :")
        lines.extend(
            f"{PAD}  {format_native_frame(frame)}"
            for frame in native_frames[:MAX_NATIVE_TRACE_FRAMES]
        )
    if snippet is not None:
        lines.append(f"{PAD}source : {sanitize(snippet.path, 200)}")
        lines.extend(f"{PAD}  {row}" for row in _snippet_lines(snippet))
    lines.extend(f"{PAD}hint   : {hint}" for hint in _hint_lines(group))
    return lines


def _summary(report: Report) -> str:
    if report.baseline_used:
        label = "new problem" if report.matching_groups == 1 else "new problems"
        text = (
            f"{_count(report.matching_groups)} {label} "
            f"({_count(report.known_hidden)} known problem(s) hidden by baseline)"
        )
    elif report.matching_groups == 0:
        text = "no runtime errors, crashes or long callbacks found"
    else:
        label = "distinct problem" if report.matching_groups == 1 else "distinct problems"
        text = f"{_count(report.matching_groups)} {label}"
    return f"{text}; {_count(report.total_events)} event(s) seen in total"


def render_text(report: Report, *, show_args: bool = False) -> str:
    sources = ", ".join(sanitize(source, 120) for source in report.sources)
    lines = [
        f"amxtriage {__version__}",
        f"input  : {sources} ({_count(report.lines_read)} lines)",
        f"result : {_summary(report)}",
        "",
    ]
    for number, group in enumerate(report.groups, start=1):
        lines.extend(
            render_group_text(
                group,
                show_args=show_args,
                snippet=report.contexts.get(group.signature_id),
                new=report.baseline_used,
                index=number,
            )
        )
        lines.append("")
    if report.omitted_groups:
        lines.append(f"... {_count(report.omitted_groups)} more problem(s) not shown (use --top)")
        lines.append("")
    if report.notes:
        lines.append("notes:")
        lines.extend(f"  - {note}" for note in report.notes)
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _fenced(rows: list[str]) -> list[str]:
    body = [row.replace("`", "'") for row in rows]
    return ["```text", *body, "```"]


def _markdown_group(number: int, group: Group, report: Report, show_args: bool) -> list[str]:
    snippet = report.contexts.get(group.signature_id)
    out = [f"## {number}. {inline_code(group_title(group), 220)}", ""]
    badge = " (new)" if report.baseline_used else ""
    out.append(f"- **Count:** {_count(group.count)}{badge}")
    out.append(f"- **Signature:** `{group.signature_id}`")
    where = format_where(group)
    if where is not None:
        out.append(f"- **Where:** {inline_code(where, 300)}")
    if group.kind == "runtime_error" and group.script:
        out.append(f"- **Script:** {inline_code(group.script, 200)}")
    out.append(f"- **Seen:** {inline_code(format_seen(group), 300)}")
    for detail in group.sample.details[:MAX_DETAIL_LINES]:
        out.append(f"- **Detail:** {inline_code(detail, 200)}")
    for hint in _hint_lines(group):
        out.append(f"- **Hint:** {sanitize(hint, 400)}")
    out.append("")
    frames = group.sample.frames[:MAX_TRACE_FRAMES]
    if frames:
        out.append("Backtrace:")
        out.append("")
        out.extend(_fenced([format_frame(frame, show_args) for frame in frames]))
        out.append("")
    if group.kind == "crash" and group.sample.native_frames:
        native = group.sample.native_frames[:MAX_NATIVE_TRACE_FRAMES]
        out.append("Native backtrace:")
        out.append("")
        out.extend(_fenced([format_native_frame(frame) for frame in native]))
        out.append("")
    if snippet is not None:
        out.append(f"Source: {inline_code(snippet.path, 200)}")
        out.append("")
        out.extend(_fenced(_snippet_lines(snippet)))
        out.append("")
    return out


def render_markdown(report: Report, *, show_args: bool = False) -> str:
    sources = ", ".join(inline_code(source, 120) for source in report.sources)
    out = [
        "# amxtriage report",
        "",
        f"- **Input:** {sources} ({_count(report.lines_read)} lines)",
        f"- **Result:** {_summary(report)}",
        f"- **Tool:** amxtriage {__version__}",
        "",
    ]
    for number, group in enumerate(report.groups, start=1):
        out.extend(_markdown_group(number, group, report, show_args))
    if report.omitted_groups:
        out.append(f"_{_count(report.omitted_groups)} more problem(s) not shown._")
        out.append("")
    if report.notes:
        out.append("**Notes**")
        out.append("")
        out.extend(f"- {note}" for note in report.notes)
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def _optional(text: str | None, limit: int = 200) -> str | None:
    return sanitize(text, limit) if text is not None else None


def _occurrence_dict(occurrence: Occurrence) -> dict[str, object]:
    return {
        "source": sanitize(occurrence.source, 120),
        "line": occurrence.line_number,
        "timestamp": _optional(occurrence.timestamp, 64),
    }


def _frame_dict(frame: Frame, show_args: bool) -> dict[str, object]:
    data: dict[str, object] = {
        "index": frame.index,
        "kind": frame.kind,
        "function": sanitize(frame.function, 128),
        "public": frame.public,
        "file": _optional(frame.file),
        "line": frame.line,
        "module": _optional(frame.module, 120),
    }
    if show_args:
        data["args"] = _optional(frame.args, ARGS_DISPLAY_LIMIT)
    return data


def group_to_dict(
    group: Group,
    *,
    show_args: bool = False,
    snippet: Snippet | None = None,
    new: bool = False,
) -> dict[str, object]:
    sample = group.sample
    data: dict[str, object] = {
        "id": group.signature_id,
        "kind": group.kind,
        "code": group.code,
        "message": _optional(group.message),
        "script": _optional(group.script),
        "function": _optional(group.function, 128),
        "file": _optional(group.file),
        "count": group.count,
        "lines": [
            {"line": line, "count": count} for line, count in group.top_lines(MAX_JSON_LINES)
        ],
        "first": _occurrence_dict(group.first),
        "last": _occurrence_dict(group.last),
        "details": [sanitize(detail, 200) for detail in sample.details],
        "backtrace": [_frame_dict(frame, show_args) for frame in sample.frames],
        "native_backtrace": [
            {
                "index": frame.index,
                "callee": sanitize(frame.callee, 128),
                "module": _optional(frame.module, 120),
            }
            for frame in sample.native_frames
        ],
        "causes": list(causes_for(group.kind, group.code)),
        "source": None,
        "new": new,
    }
    if snippet is not None:
        data["source"] = {
            "path": sanitize(snippet.path, 200),
            "first_line": snippet.first_line,
            "target_line": snippet.target_line,
            "lines": list(snippet.lines),
        }
    return data


def render_json(report: Report, *, show_args: bool = False) -> str:
    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "tool": {"name": "amxtriage", "version": __version__},
        "summary": {
            "sources": [sanitize(source, 120) for source in report.sources],
            "lines_read": report.lines_read,
            "truncated_lines": report.truncated_lines,
            "events": report.total_events,
            "dropped_events": report.dropped_events,
            "ignored_interrupts": report.ignored_interrupts,
            "matching_problems": report.matching_groups,
            "shown_problems": len(report.groups),
            "omitted_problems": report.omitted_groups,
            "known_hidden": report.known_hidden,
            "baseline_used": report.baseline_used,
        },
        "notes": list(report.notes),
        "problems": [
            group_to_dict(
                group,
                show_args=show_args,
                snippet=report.contexts.get(group.signature_id),
                new=report.baseline_used,
            )
            for group in report.groups
        ],
    }
    return json.dumps(payload, indent=2) + "\n"


def render_report(report: Report, output_format: str, *, show_args: bool = False) -> str:
    if output_format == "json":
        return render_json(report, show_args=show_args)
    if output_format == "markdown":
        return render_markdown(report, show_args=show_args)
    return render_text(report, show_args=show_args)


def render_explain(error: AmxError) -> str:
    lines = [f"AMX error {error.code}: {error.name}", ""]
    if error.causes:
        lines.append("Common causes and checks:")
        lines.extend(f"  - {cause}" for cause in error.causes)
    else:
        lines.append("No extra guidance is available for this code.")
    lines.append("")
    lines.append(
        "These are common causes, not a diagnosis. The backtrace in the log is the evidence."
    )
    return "\n".join(lines) + "\n"


def render_error_list() -> str:
    lines = ["AMX error codes (use 'amxtriage explain CODE' for details):", ""]
    lines.extend(f"  {error.code:>2}  {error.name}" for error in all_errors() if error.code != 0)
    return "\n".join(lines) + "\n"
