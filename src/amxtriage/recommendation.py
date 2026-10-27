"""Rule-based, offline remediation guidance for AMX runtime diagnostics.

Recommendations are intentionally advisory. Log text is not enough to prove that a
source edit preserves a script's intended behaviour, so this module never writes files.
"""

from dataclasses import dataclass
from typing import Literal

from amxtriage.analysis import Report
from amxtriage.model import Group
from amxtriage.render import format_where
from amxtriage.source import Snippet
from amxtriage.textutil import inline_code, sanitize

Severity = Literal["critical", "high", "medium", "low"]
Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True, slots=True)
class Recommendation:
    signature_id: str
    title: str
    severity: Severity
    confidence: Confidence
    occurrences: int
    where: str | None
    diagnosis: str
    actions: tuple[str, ...]
    example: str | None
    source: Snippet | None
    automatic_fix: bool = False


Rule = tuple[str, Severity, Confidence, tuple[str, ...], str | None]

_RULES: dict[tuple[str, int | None], Rule] = {
    ("runtime_error", 2): (
        "Assertion failed",
        "high",
        "high",
        (
            "Inspect the assert condition at the reported location and identify which assumption "
            "became false.",
            "Validate user input and state before the assertion; keep assert for invariants that "
            "should never fail.",
            "Add a regression case for the input or state that triggered this condition.",
        ),
        None,
    ),
    ("runtime_error", 3): (
        "Stack/heap collision",
        "critical",
        "medium",
        (
            "Check large local arrays, recursive calls, and paths that allocate variable-sized "
            "data.",
            "Measure current stack/heap use before changing #pragma dynamic; increasing it "
            "consumes "
            "more memory and may only hide the cause.",
            "Retest with realistic player counts and the same server/plugin build.",
        ),
        None,
    ),
    ("runtime_error", 4): (
        "Array index out of bounds",
        "high",
        "high",
        (
            "Trace the expression used as the array index and check its minimum and maximum "
            "values.",
            "Check loop termination, player/vehicle IDs, and whether the index is a count or a "
            "zero-based position.",
            "Add a regression test for the first invalid index and the highest valid index.",
        ),
        "if (index >= 0 && index < sizeof values) {\n    values[index] = new_value;\n}",
    ),
    ("runtime_error", 5): (
        "Invalid memory access",
        "critical",
        "low",
        (
            "Inspect the AMX frame and any native called from that function; the invalid address "
            "may originate in native/plugin code.",
            "Check array/string buffer sizes and the arguments passed to natives.",
            "Reproduce with debug symbols and test the same plugin versions before attributing the "
            "fault to Pawn code.",
        ),
        None,
    ),
    ("runtime_error", 10): (
        "Native function failed",
        "high",
        "medium",
        (
            "Inspect the failing native's return value and its own log messages.",
            "Validate handles, IDs, connection state, and arguments before calling the native.",
            "Check the provider plugin's documentation and version compatibility.",
        ),
        None,
    ),
    ("runtime_error", 11): (
        "Divide by zero",
        "high",
        "high",
        (
            "Find the divisor in the reported expression; modulo operations can fail for the same "
            "reason.",
            "Choose the correct application behaviour when the divisor is zero (skip, return an "
            "error, or use a documented fallback).",
            "Add tests for zero, negative values where valid, and normal values.",
        ),
        (
            "if (divisor != 0) {\n"
            "    result = numerator / divisor;\n"
            "} else {\n"
            "    // Handle the zero case for your game logic.\n"
            "}"
        ),
    ),
    ("runtime_error", 16): (
        "Out of memory",
        "critical",
        "medium",
        (
            "Review large global arrays, dynamic allocations, and memory held by plugins.",
            "Estimate memory per player and test at the server's expected capacity.",
            "Do not increase array sizes until the memory budget has been measured.",
        ),
        None,
    ),
    ("runtime_error", 19): (
        "File or function is not found",
        "high",
        "high",
        (
            "Read the missing native/function names in the complete log details.",
            "Confirm the provider plugin is installed, loads successfully, and matches the server "
            "OS and architecture.",
            "Check include declarations and plugin load order; an include file alone does not "
            "install "
            "a native implementation.",
        ),
        None,
    ),
    ("runtime_error", 20): (
        "Invalid callback entry point",
        "high",
        "medium",
        (
            "Check whether the callback is declared public and has the expected name and "
            "signature.",
            "Recompile the script after changing the callback, then verify the server loads "
            "the new "
            ".amx file.",
        ),
        None,
    ),
}


def _fallback(group: Group) -> tuple[str, Severity, Confidence, tuple[str, ...], str | None]:
    if group.kind == "crash":
        return (
            "Native server crash",
            "critical",
            "low",
            (
                "Compare the AMX backtrace with the native backtrace; the crashing module is "
                "a lead, "
                "not proof of root cause.",
                "Reproduce with matching server and plugin versions, then update or isolate one "
                "plugin at a time.",
                "Preserve the full crash log and symbols before changing code.",
            ),
            None,
        )
    if group.kind == "long_call":
        return (
            "Long callback execution",
            "medium",
            "medium",
            (
                "Profile the callback named in the AMX backtrace and find the loop or operation "
                "dominating execution time.",
                "Avoid blocking database/file/network work in frequently called callbacks; "
                "batch or "
                "defer work where the framework permits.",
                "Measure again with representative load after each change.",
            ),
            None,
        )
    if group.kind == "runtime_error" and group.code == 9:
        return (
            "Native callback unavailable",
            "high",
            "medium",
            (
                "Check the native callback and provider plugin expected by the script.",
                "Confirm the plugin loaded correctly and exports the native expected by the "
                "compiled "
                "script.",
            ),
            None,
        )
    return (
        "Review AMX runtime diagnostic",
        "medium",
        "low",
        (
            "Run `amxtriage explain <CODE>` for the known error-code notes.",
            "Inspect the reported source location and surrounding calls; the log alone may not "
            "identify the root cause.",
            "Add a regression test or repeatable server scenario before accepting a source change.",
        ),
        None,
    )


def recommend_group(group: Group, source: Snippet | None = None) -> Recommendation:
    rule = _RULES.get((group.kind, group.code))
    title, severity, confidence, actions, example = rule or _fallback(group)
    where = format_where(group)
    diagnosis = (
        f"{title} was recorded {group.count} time(s). "
        "This is a rule-based explanation, not proof of the root cause."
    )
    return Recommendation(
        signature_id=group.signature_id,
        title=title,
        severity=severity,
        confidence=confidence,
        occurrences=group.count,
        where=where,
        diagnosis=diagnosis,
        actions=actions,
        example=example,
        source=source,
    )


def recommendations_for_report(report: Report) -> list[Recommendation]:
    return [
        recommend_group(group, report.contexts.get(group.signature_id)) for group in report.groups
    ]


def _snippet_text(snippet: Snippet) -> str:
    width = len(str(snippet.first_line + len(snippet.lines) - 1))
    rows = []
    for offset, line in enumerate(snippet.lines):
        number = snippet.first_line + offset
        marker = ">" if number == snippet.target_line else " "
        safe_line = line.replace("`", "'")
        rows.append(f"{marker} {number:>{width}} | {safe_line}")
    return "\n".join(rows)


def render_recommendations(report: Report, output_format: str) -> str:
    items = recommendations_for_report(report)
    if output_format == "json":
        import json

        payload: dict[str, object] = {
            "schema_version": 1,
            "tool": "amxtriage",
            "mode": "rule-based-recommendations",
            "automatic_changes_applied": False,
            "input": report.sources,
            "problems": [
                {
                    "id": item.signature_id,
                    "title": sanitize(item.title, 200),
                    "severity": item.severity,
                    "confidence": item.confidence,
                    "occurrences": item.occurrences,
                    "where": sanitize(item.where, 300) if item.where else None,
                    "diagnosis": sanitize(item.diagnosis, 500),
                    "actions": [sanitize(action, 500) for action in item.actions],
                    "example": item.example,
                    "source": (
                        {
                            "path": sanitize(item.source.path, 200),
                            "target_line": item.source.target_line,
                            "lines": list(item.source.lines),
                        }
                        if item.source
                        else None
                    ),
                    "automatic_fix_available": False,
                }
                for item in items
            ],
            "notes": [
                "No source files were modified.",
                "Examples are templates, not drop-in fixes; adapt and test them before use.",
            ],
        }
        return json.dumps(payload, indent=2) + "\n"

    markdown = output_format == "markdown"
    heading = (
        "# amxtriage recommendations"
        if markdown
        else f"amxtriage recommendations ({len(items)} issue(s))"
    )
    lines = [
        heading,
        "",
        "These are offline, rule-based suggestions. No source files were modified.",
        "Examples are templates, not drop-in fixes; adapt them to your actual variables and game "
        "logic.",
        "",
    ]
    for number, item in enumerate(items, start=1):
        heading = f"## {number}. {item.title}" if markdown else f"[{number}] {item.title}"
        lines.extend(
            [
                heading,
                f"Severity: {item.severity}; confidence: {item.confidence}; "
                f"occurrences: {item.occurrences}",
                f"Signature: {item.signature_id}",
            ]
        )
        if item.where:
            where = inline_code(item.where, 300) if markdown else sanitize(item.where, 300)
            lines.append(f"Where: {where}")
        lines.extend(["Diagnosis:", item.diagnosis, "Recommended checks:"])
        lines.extend(f"- {action}" for action in item.actions)
        if item.example:
            lines.extend(["Illustrative Pawn pattern:", "```pawn", item.example, "```"])
        if item.source:
            source_path = (
                inline_code(item.source.path, 200) if markdown else sanitize(item.source.path, 200)
            )
            lines.extend(
                [f"Source context: {source_path}", "```text", _snippet_text(item.source), "```"]
            )
        lines.extend(["Automatic fix: unavailable for this rule; no changes were applied.", ""])
    if not items:
        lines.append("No reportable AMX errors, crashes, or long callbacks were found.")
    return "\n".join(lines).rstrip() + "\n"
