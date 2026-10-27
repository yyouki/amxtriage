import json

from amxtriage import __version__
from amxtriage.amxerrors import AmxError, all_errors, causes_for
from amxtriage.analysis import Report
from amxtriage.localization import translate as tr
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


def group_title(group: Group, language: str = "en") -> str:
    if group.kind == "crash":
        if group.script:
            return tr(language, "crash_while").format(script=sanitize(group.script, 200))
        return tr(language, "crash")
    if group.kind == "long_call":
        return tr(language, "long_callback")
    message = sanitize(group.message or tr(language, "unknown_error"), 200)
    return tr(language, "runtime_error").format(code=group.code, message=message)


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


def format_seen(group: Group, language: str = "en") -> str:
    if group.count == 1:
        return tr(language, "at").format(first=format_occurrence(group.first))
    return tr(language, "first_last").format(
        first=format_occurrence(group.first), last=format_occurrence(group.last)
    )


def format_where(group: Group, language: str = "en") -> str | None:
    if group.function is None:
        return None
    text = sanitize(group.function, 128)
    ranked = group.top_lines(3)
    if group.file is None or not ranked:
        return f"{text}  {tr(language, 'no_file_line')}"
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


def _hint_lines(group: Group, language: str = "en") -> list[str]:
    causes = causes_for(group.kind, group.code)
    if not causes:
        return []
    text = causes[0]
    if group.kind == "runtime_error" and group.code is not None and len(causes) > 1:
        text += f" {tr(language, 'more_explain').format(code=group.code)}"
    return [text]


def render_group_text(
    group: Group,
    *,
    show_args: bool = False,
    snippet: Snippet | None = None,
    new: bool = False,
    index: int | None = None,
    language: str = "en",
) -> list[str]:
    label = f"[{index}] " if index is not None else ""
    badge = "NEW  " if new else ""
    lines = [
        f"{label}{badge}{group_title(group, language)}   x{_count(group.count)}"
        f"   id={group.signature_id}"
    ]
    where = format_where(group, language)
    if where is not None:
        lines.append(f"{PAD}{tr(language, 'where_label')} {where}")
    if group.kind == "runtime_error" and group.script:
        lines.append(f"{PAD}{tr(language, 'script_label')} {sanitize(group.script, 200)}")
    lines.append(f"{PAD}{tr(language, 'seen_label')} {format_seen(group, language)}")
    details = group.sample.details
    lines.extend(
        f"{PAD}{tr(language, 'detail_label')} {sanitize(detail, 200)}"
        for detail in details[:MAX_DETAIL_LINES]
    )
    if len(details) > MAX_DETAIL_LINES:
        lines.append(
            f"{PAD}{tr(language, 'detail_label')} ... {len(details) - MAX_DETAIL_LINES} more"
        )
    frames = group.sample.frames
    if frames:
        lines.append(f"{PAD}{tr(language, 'trace_label')}")
        lines.extend(
            f"{PAD}  {format_frame(frame, show_args)}" for frame in frames[:MAX_TRACE_FRAMES]
        )
        if len(frames) > MAX_TRACE_FRAMES:
            lines.append(f"{PAD}  ... {len(frames) - MAX_TRACE_FRAMES} more frame(s)")
    native_frames = group.sample.native_frames
    if group.kind == "crash" and native_frames:
        lines.append(f"{PAD}{tr(language, 'native_label')}")
        lines.extend(
            f"{PAD}  {format_native_frame(frame)}"
            for frame in native_frames[:MAX_NATIVE_TRACE_FRAMES]
        )
    if snippet is not None:
        lines.append(f"{PAD}{tr(language, 'source_label')} {sanitize(snippet.path, 200)}")
        lines.extend(f"{PAD}  {row}" for row in _snippet_lines(snippet))
    lines.extend(
        f"{PAD}{tr(language, 'hint_label')} {hint}" for hint in _hint_lines(group, language)
    )
    return lines


def _summary(report: Report, language: str = "en") -> str:
    if report.baseline_used:
        label = tr(
            language, "new_problem_one" if report.matching_groups == 1 else "new_problem_many"
        )
        hidden = tr(language, "known_hidden").format(count=_count(report.known_hidden))
        text = tr(language, "summary_baseline").format(
            count=_count(report.matching_groups), label=label, hidden=hidden
        )
    elif report.matching_groups == 0:
        text = tr(language, "no_problems")
    else:
        label = tr(language, "distinct_one" if report.matching_groups == 1 else "distinct_many")
        text = tr(language, "summary_distinct").format(
            count=_count(report.matching_groups), label=label
        )
    return tr(language, "summary_total").format(text=text, events=_count(report.total_events))


def render_text(report: Report, *, show_args: bool = False, language: str = "en") -> str:
    sources = ", ".join(sanitize(source, 120) for source in report.sources)
    lines = [
        f"amxtriage {__version__}",
        f"{tr(language, 'input_label')} {sources} ({_count(report.lines_read)} lines)",
        f"{tr(language, 'result_label')} {_summary(report, language)}",
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
                language=language,
            )
        )
        lines.append("")
    if report.omitted_groups:
        lines.append(tr(language, "omitted").format(count=_count(report.omitted_groups)))
        lines.append("")
    if report.notes:
        lines.append(tr(language, "notes_label"))
        lines.extend(f"  - {note}" for note in report.notes)
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _fenced(rows: list[str]) -> list[str]:
    body = [row.replace("`", "'") for row in rows]
    return ["```text", *body, "```"]


def _markdown_group(
    number: int, group: Group, report: Report, show_args: bool, language: str = "en"
) -> list[str]:
    snippet = report.contexts.get(group.signature_id)
    out = [f"## {number}. {inline_code(group_title(group, language), 220)}", ""]
    badge = f" ({tr(language, 'md_new')})" if report.baseline_used else ""
    out.append(f"- **{tr(language, 'md_count')}:** {_count(group.count)}{badge}")
    out.append(f"- **{tr(language, 'md_signature')}:** `{group.signature_id}`")
    where = format_where(group, language)
    if where is not None:
        out.append(f"- **{tr(language, 'md_where')}:** {inline_code(where, 300)}")
    if group.kind == "runtime_error" and group.script:
        out.append(f"- **{tr(language, 'md_script')}:** {inline_code(group.script, 200)}")
    out.append(f"- **{tr(language, 'md_seen')}:** {inline_code(format_seen(group, language), 300)}")
    for detail in group.sample.details[:MAX_DETAIL_LINES]:
        out.append(f"- **{tr(language, 'md_detail')}:** {inline_code(detail, 200)}")
    for hint in _hint_lines(group, language):
        out.append(f"- **{tr(language, 'md_hint')}:** {sanitize(hint, 400)}")
    out.append("")
    frames = group.sample.frames[:MAX_TRACE_FRAMES]
    if frames:
        out.append(f"{tr(language, 'md_backtrace')}:")
        out.append("")
        out.extend(_fenced([format_frame(frame, show_args) for frame in frames]))
        out.append("")
    if group.kind == "crash" and group.sample.native_frames:
        native = group.sample.native_frames[:MAX_NATIVE_TRACE_FRAMES]
        out.append(f"{tr(language, 'md_native_backtrace')}:")
        out.append("")
        out.extend(_fenced([format_native_frame(frame) for frame in native]))
        out.append("")
    if snippet is not None:
        out.append(f"{tr(language, 'md_source')}: {inline_code(snippet.path, 200)}")
        out.append("")
        out.extend(_fenced(_snippet_lines(snippet)))
        out.append("")
    return out


def render_markdown(report: Report, *, show_args: bool = False, language: str = "en") -> str:
    sources = ", ".join(inline_code(source, 120) for source in report.sources)
    out = [
        tr(language, "md_report_title"),
        "",
        f"- **{tr(language, 'md_input')}:** {sources} ({_count(report.lines_read)} lines)",
        f"- **{tr(language, 'md_result')}:** {_summary(report, language)}",
        f"- **{tr(language, 'md_tool')}:** amxtriage {__version__}",
        "",
    ]
    for number, group in enumerate(report.groups, start=1):
        out.extend(_markdown_group(number, group, report, show_args, language))
    if report.omitted_groups:
        out.append(tr(language, "md_omitted").format(count=_count(report.omitted_groups)))
        out.append("")
    if report.notes:
        out.append(tr(language, "md_notes"))
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


def render_report(
    report: Report, output_format: str, *, show_args: bool = False, language: str = "en"
) -> str:
    if output_format == "json":
        return render_json(report, show_args=show_args)
    if output_format == "markdown":
        return render_markdown(report, show_args=show_args, language=language)
    return render_text(report, show_args=show_args, language=language)


def render_explain(error: AmxError, language: str = "en") -> str:
    lines = [tr(language, "explain_title").format(code=error.code, name=error.name), ""]
    if error.causes:
        lines.append(tr(language, "common_causes"))
        lines.extend(f"  - {cause}" for cause in error.causes)
    else:
        lines.append(tr(language, "no_guidance"))
    lines.append("")
    lines.append(tr(language, "explain_uncertainty"))
    return "\n".join(lines) + "\n"


def render_error_list(language: str = "en") -> str:
    lines = [tr(language, "error_list_title"), ""]
    lines.extend(f"  {error.code:>2}  {error.name}" for error in all_errors() if error.code != 0)
    return "\n".join(lines) + "\n"
