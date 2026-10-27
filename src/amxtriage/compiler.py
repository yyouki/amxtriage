"""Parse saved compiler/linter output without executing source code or tool commands."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from amxtriage import __version__
from amxtriage.localization import translate as tr
from amxtriage.reader import LineSplitter, display_name, iter_lines, open_log
from amxtriage.textutil import inline_code, sanitize

COMPILER_LANGUAGES = (
    "auto",
    "pawn",
    "python",
    "javascript",
    "typescript",
    "c_cpp",
    "java",
    "csharp",
    "go",
    "rust",
)
MAX_DIAGNOSTICS = 10_000

_PAWN = re.compile(
    r"^\s*(?P<file>.+?)\((?P<line>\d+)\)\s*:\s*"
    r"(?P<severity>fatal error|error|warning|note)\s*"
    r"(?:(?P<code>\d+)\s*)?:\s*(?P<message>.*)$",
    re.IGNORECASE,
)
_PAREN = re.compile(
    r"^\s*(?P<file>.+?)\((?P<line>\d+)(?:,(?P<column>\d+))?\)\s*:\s*"
    r"(?P<severity>fatal error|error|warning|note)\s*"
    r"(?P<code>[A-Z]{1,4}\d+)?\s*:\s*(?P<message>.*)$",
    re.IGNORECASE,
)
_COLON = re.compile(
    r"^\s*(?P<file>.+?):(?P<line>\d+):(?P<column>\d+):\s*"
    r"(?:(?P<severity>fatal error|error|warning|note)\s*:\s*)?"
    r"(?P<message>.*)$",
    re.IGNORECASE,
)
_JAVA = re.compile(
    r"^\s*(?P<file>.+?\.java):(?P<line>\d+):\s*"
    r"(?P<severity>error|warning|note):\s*(?P<message>.*)$",
    re.IGNORECASE,
)
_PY_FILE = re.compile(r'^\s*File "(?P<file>.+?)", line (?P<line>\d+)')
_PY_EXCEPTION = re.compile(
    r"^\s*(?P<code>[A-Za-z_][A-Za-z0-9_.]*"
    r"(?:Error|Exception|Warning|Interrupt|Exit|Fault|Failure)?):\s*(?P<message>.*)$"
)
_RUST_HEAD = re.compile(
    r"^\s*(?P<severity>error|warning|note)"
    r"(?:\[(?P<code>E\d+)\])?:\s*(?P<message>.*)$",
    re.IGNORECASE,
)
_RUST_ARROW = re.compile(r"^\s*-->\s*(?P<file>.+?):(?P<line>\d+):(?P<column>\d+)\s*$")
_ESLINT_LINE = re.compile(
    r"^\s*(?P<line>\d+):(?P<column>\d+)\s+"
    r"(?P<severity>error|warning)\s+(?P<message>.+?)"
    r"(?:\s{2,}(?P<code>[\w/@.-]+))?\s*$",
    re.IGNORECASE,
)

_EXTENSIONS = {
    ".pwn": "pawn",
    ".inc": "pawn",
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".c": "c_cpp",
    ".h": "c_cpp",
    ".cc": "c_cpp",
    ".cpp": "c_cpp",
    ".cxx": "c_cpp",
    ".hpp": "c_cpp",
    ".java": "java",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
}


@dataclass(frozen=True, slots=True)
class CompilerDiagnostic:
    diagnostic_id: str
    source_language: str
    file: str | None
    line: int | None
    column: int | None
    severity: str
    code: str | None
    message: str
    hint_key: str


@dataclass(slots=True)
class CompilerReport:
    sources: list[str]
    requested_language: str
    lines_read: int
    truncated_lines: int
    diagnostics: list[CompilerDiagnostic]
    dropped_diagnostics: int


def _extension_language(path: str | None) -> str | None:
    if not path:
        return None
    suffix = Path(path.replace("\\", "/")).suffix.lower()
    return _EXTENSIONS.get(suffix)


def _stable_id(
    language: str,
    path: str | None,
    line: int | None,
    column: int | None,
    severity: str,
    code: str | None,
    message: str,
) -> str:
    identity = "\0".join(
        str(part)
        for part in (language, path or "", line or "", column or "", severity, code or "", message)
    )
    return hashlib.sha256(identity.encode("utf-8", errors="replace")).hexdigest()[:16]


def _hint(message: str) -> str:
    lowered = message.casefold()
    if any(
        token in lowered
        for token in (
            "include file",
            "module not found",
            "no such file",
            "file not found",
            "cannot open include",
            "cannot find module",
            "cannot find symbol",
            "could not find",
        )
    ):
        return "compiler_hint_missing"
    if any(
        token in lowered
        for token in (
            "undefined symbol",
            "is not defined",
            "cannot find name",
            "not found",
            "unresolved external",
        )
    ):
        return "compiler_hint_undefined"
    if any(
        token in lowered
        for token in (
            "type mismatch",
            "incompatible types",
            "cannot use ",
            "not assignable",
            "cannot convert",
            "expected type",
            "mismatched types",
        )
    ):
        return "compiler_hint_type"
    if any(
        token in lowered
        for token in (
            "syntax error",
            "expected ';'",
            "expected expression",
            "unexpected token",
            "unexpected symbol",
            "unterminated",
        )
    ):
        return "compiler_hint_syntax"
    return "compiler_hint_generic"


def _make_diagnostic(
    *,
    requested_language: str,
    file: str | None,
    line: int | None,
    column: int | None,
    severity: str,
    code: str | None,
    message: str,
) -> CompilerDiagnostic:
    language = (
        requested_language
        if requested_language != "auto"
        else (_extension_language(file) or "unknown")
    )
    normal_severity = severity.strip().lower()
    if normal_severity not in {"error", "warning", "note", "fatal error"}:
        normal_severity = "error"
    safe_message = sanitize(message.strip() or "no diagnostic message", 2000)
    safe_file = sanitize(file.strip(), 500) if file else None
    safe_code = sanitize(code.strip(), 64) if code else None
    identifier = _stable_id(
        language, safe_file, line, column, normal_severity, safe_code, safe_message
    )
    return CompilerDiagnostic(
        diagnostic_id=identifier,
        source_language=language,
        file=safe_file,
        line=line,
        column=column,
        severity=normal_severity,
        code=safe_code,
        message=safe_message,
        hint_key=_hint(safe_message),
    )


def parse_compiler_lines(
    lines: Iterable[str],
    *,
    source_language: str = "auto",
    limit: int = MAX_DIAGNOSTICS,
) -> tuple[list[CompilerDiagnostic], int]:
    """Parse common saved compiler formats while preserving structured source locations."""
    if source_language not in COMPILER_LANGUAGES:
        raise ValueError(f"unsupported source language: {source_language}")
    diagnostics: list[CompilerDiagnostic] = []
    dropped = 0
    python_frame: tuple[str, int] | None = None
    rust_pending: tuple[str, str | None, str] | None = None
    eslint_file: str | None = None

    def emit(diagnostic: CompilerDiagnostic) -> None:
        nonlocal dropped
        if len(diagnostics) < max(0, limit):
            diagnostics.append(diagnostic)
        else:
            dropped += 1

    for raw_line in lines:
        line_text = raw_line.rstrip("\r\n")

        if source_language in {"auto", "rust"}:
            rust_head = _RUST_HEAD.match(line_text)
            if rust_head and (source_language == "rust" or rust_head.group("code")):
                if rust_pending is not None:
                    severity, code, message = rust_pending
                    emit(
                        _make_diagnostic(
                            requested_language="rust",
                            file=None,
                            line=None,
                            column=None,
                            severity=severity,
                            code=code,
                            message=message,
                        )
                    )
                rust_pending = (
                    rust_head.group("severity").lower(),
                    rust_head.group("code"),
                    rust_head.group("message"),
                )
                continue
            rust_arrow = _RUST_ARROW.match(line_text)
            if rust_pending is not None and rust_arrow:
                severity, code, message = rust_pending
                emit(
                    _make_diagnostic(
                        requested_language="rust",
                        file=rust_arrow.group("file"),
                        line=int(rust_arrow.group("line")),
                        column=int(rust_arrow.group("column")),
                        severity=severity,
                        code=code,
                        message=message,
                    )
                )
                rust_pending = None
                continue

        if source_language in {"auto", "python"}:
            python_match = _PY_FILE.match(line_text)
            if python_match and (
                source_language == "python"
                or _extension_language(python_match.group("file")) == "python"
            ):
                python_frame = (python_match.group("file"), int(python_match.group("line")))
                continue
            exception_match = _PY_EXCEPTION.match(line_text)
            if exception_match and (python_frame is not None or source_language == "python"):
                file, source_line = python_frame if python_frame else (None, None)
                emit(
                    _make_diagnostic(
                        requested_language="python",
                        file=file,
                        line=source_line,
                        column=None,
                        severity="error",
                        code=exception_match.group("code"),
                        message=exception_match.group("message"),
                    )
                )
                python_frame = None
                continue

        stripped = line_text.strip()
        if source_language in {"auto", "javascript", "typescript"} and stripped:
            suffix_language = _extension_language(stripped)
            if stripped.lower().endswith((".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")) and (
                source_language == "auto" or source_language == suffix_language
            ):
                eslint_file = stripped
                continue
            eslint_match = _ESLINT_LINE.match(line_text)
            if eslint_match and eslint_file:
                inferred = _extension_language(eslint_file) or source_language
                compatible = (
                    source_language == "auto"
                    or source_language == inferred
                    or (source_language == "javascript" and inferred == "javascript")
                )
                if compatible:
                    emit(
                        _make_diagnostic(
                            requested_language=inferred,
                            file=eslint_file,
                            line=int(eslint_match.group("line")),
                            column=int(eslint_match.group("column")),
                            severity=eslint_match.group("severity").lower(),
                            code=eslint_match.group("code"),
                            message=eslint_match.group("message"),
                        )
                    )
                    continue

        pawn_match = _PAWN.match(line_text)
        if pawn_match and source_language in {"auto", "pawn"}:
            inferred = _extension_language(pawn_match.group("file"))
            if source_language == "pawn" or inferred == "pawn" or pawn_match.group("code"):
                emit(
                    _make_diagnostic(
                        requested_language="pawn",
                        file=pawn_match.group("file"),
                        line=int(pawn_match.group("line")),
                        column=None,
                        severity=pawn_match.group("severity"),
                        code=pawn_match.group("code"),
                        message=pawn_match.group("message"),
                    )
                )
                continue

        paren_match = _PAREN.match(line_text)
        if paren_match and source_language in {"auto", "typescript", "csharp"}:
            file_language = _extension_language(paren_match.group("file"))
            code = paren_match.group("code")
            inferred = (
                "typescript"
                if code and code.upper().startswith("TS")
                else "csharp"
                if code and code.upper().startswith("CS")
                else file_language
            )
            compatible = (
                source_language == "auto" and inferred in {"typescript", "csharp"}
            ) or source_language == inferred
            if compatible:
                emit(
                    _make_diagnostic(
                        requested_language=inferred or source_language,
                        file=paren_match.group("file"),
                        line=int(paren_match.group("line")),
                        column=int(paren_match.group("column"))
                        if paren_match.group("column")
                        else None,
                        severity=paren_match.group("severity"),
                        code=code,
                        message=paren_match.group("message"),
                    )
                )
                continue

        java_match = _JAVA.match(line_text)
        if java_match and source_language in {"auto", "java"}:
            emit(
                _make_diagnostic(
                    requested_language="java",
                    file=java_match.group("file"),
                    line=int(java_match.group("line")),
                    column=None,
                    severity=java_match.group("severity"),
                    code=None,
                    message=java_match.group("message"),
                )
            )
            continue

        colon_match = _COLON.match(line_text)
        if colon_match:
            file = colon_match.group("file")
            inferred = _extension_language(file)
            has_severity = colon_match.group("severity") is not None
            compatible = (
                (source_language == "auto" and inferred == "c_cpp" and has_severity)
                or (source_language == "c_cpp" and has_severity)
                or (source_language == "auto" and inferred == "go")
                or source_language == "go"
            )
            if compatible:
                severity = colon_match.group("severity") or "error"
                emit(
                    _make_diagnostic(
                        requested_language=inferred or source_language,
                        file=file,
                        line=int(colon_match.group("line")),
                        column=int(colon_match.group("column")),
                        severity=severity,
                        code=None,
                        message=colon_match.group("message"),
                    )
                )

    if rust_pending is not None:
        severity, code, message = rust_pending
        emit(
            _make_diagnostic(
                requested_language="rust",
                file=None,
                line=None,
                column=None,
                severity=severity,
                code=code,
                message=message,
            )
        )
    return diagnostics, dropped


def analyze_compiler_outputs(
    paths: Sequence[str],
    *,
    source_language: str = "auto",
    max_input_bytes: int | None = None,
    max_diagnostics: int = MAX_DIAGNOSTICS,
) -> CompilerReport:
    if source_language not in COMPILER_LANGUAGES:
        raise ValueError(f"unsupported source language: {source_language}")
    sources: list[str] = []
    diagnostics: list[CompilerDiagnostic] = []
    lines_read = 0
    truncated_lines = 0
    dropped = 0
    for path in paths:
        label = display_name(path)
        sources.append(label)
        splitter = LineSplitter()
        with open_log(path) as stream:
            remaining = max(0, max_diagnostics - len(diagnostics))
            found, omitted = parse_compiler_lines(
                iter_lines(stream, splitter, path, max_input_bytes),
                source_language=source_language,
                limit=remaining,
            )
        diagnostics.extend(found)
        dropped += omitted
        lines_read += splitter.lines
        truncated_lines += splitter.truncated
    return CompilerReport(
        sources=sources,
        requested_language=source_language,
        lines_read=lines_read,
        truncated_lines=truncated_lines,
        diagnostics=diagnostics,
        dropped_diagnostics=dropped,
    )


def _severity_label(severity: str, language: str) -> str:
    key = {
        "error": "compiler_error",
        "warning": "compiler_warning",
        "note": "compiler_note",
        "fatal error": "compiler_fatal",
    }.get(severity, "compiler_unknown")
    return tr(language, key)


def _diagnostic_dict(diagnostic: CompilerDiagnostic, language: str) -> dict[str, object]:
    return {
        "diagnostic_id": diagnostic.diagnostic_id,
        "source_language": diagnostic.source_language,
        "file": diagnostic.file,
        "line": diagnostic.line,
        "column": diagnostic.column,
        "severity": diagnostic.severity,
        "code": diagnostic.code,
        "message": diagnostic.message,
        "hint": tr(language, diagnostic.hint_key),
    }


def render_compiler_report(
    report: CompilerReport,
    output_format: str = "text",
    *,
    language: str = "en",
) -> str:
    if output_format == "json":
        payload: dict[str, object] = {
            "schema_version": 1,
            "tool": {"name": "amxtriage", "version": __version__},
            "mode": "compiler-diagnostics",
            "requested_language": report.requested_language,
            "sources": list(report.sources),
            "lines_read": report.lines_read,
            "truncated_lines": report.truncated_lines,
            "diagnostic_count": len(report.diagnostics),
            "dropped_diagnostics": report.dropped_diagnostics,
            "diagnostics": [_diagnostic_dict(item, language) for item in report.diagnostics],
            "notes": [tr(language, "compiler_no_findings_note") if not report.diagnostics else ""],
        }
        payload["notes"] = [note for note in payload["notes"] if note]
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    title = tr(language, "compiler_title")
    if output_format == "markdown":
        lines = [
            f"# {title}",
            "",
            f"- **{tr(language, 'compiler_inputs')}:** "
            f"{', '.join(inline_code(item, 200) for item in report.sources)}",
            f"- **{tr(language, 'compiler_source_language')}:** {report.requested_language}",
            f"- **{tr(language, 'compiler_count')}:** {len(report.diagnostics)}",
            "",
        ]
        for index, item in enumerate(report.diagnostics, start=1):
            where = inline_code(item.file or "<unknown file>", 500)
            if item.line is not None:
                where += f":{item.line}"
                if item.column is not None:
                    where += f":{item.column}"
            lines.extend(
                [
                    f"## {index}. {inline_code(_severity_label(item.severity, language), 80)} "
                    f"{where}",
                    "",
                    f"- **{tr(language, 'compiler_message')}:** {inline_code(item.message, 2000)}",
                    f"- **{tr(language, 'compiler_source_language')}:** {item.source_language}",
                    f"- **{tr(language, 'compiler_code')}:** {inline_code(item.code or '-', 80)}",
                    f"- **{tr(language, 'compiler_hint')}:** {tr(language, item.hint_key)}",
                    "",
                ]
            )
        if not report.diagnostics:
            lines.extend(
                [tr(language, "compiler_no_findings"), tr(language, "compiler_no_findings_note")]
            )
        if report.dropped_diagnostics:
            lines.append(tr(language, "compiler_dropped").format(count=report.dropped_diagnostics))
        return "\n".join(lines).rstrip() + "\n"

    lines = [
        f"{title} — amxtriage {__version__}",
        f"{tr(language, 'compiler_inputs')}: {', '.join(report.sources)}",
        f"{tr(language, 'compiler_source_language')}: {report.requested_language}",
        f"{tr(language, 'compiler_count')}: {len(report.diagnostics)}",
        "",
    ]
    for index, item in enumerate(report.diagnostics, start=1):
        location = item.file or "<unknown file>"
        if item.line is not None:
            location += f":{item.line}"
            if item.column is not None:
                location += f":{item.column}"
        lines.extend(
            [
                f"[{index}] {_severity_label(item.severity, language).upper()} "
                f"[{item.source_language}] {sanitize(location, 600)}",
                f"    {tr(language, 'compiler_code')}: {item.code or '-'}",
                f"    {tr(language, 'compiler_message')}: {item.message}",
                f"    {tr(language, 'compiler_hint')}: {tr(language, item.hint_key)}",
                f"    ID: {item.diagnostic_id}",
                "",
            ]
        )
    if not report.diagnostics:
        lines.extend(
            [
                tr(language, "compiler_no_findings"),
                tr(language, "compiler_no_findings_note"),
            ]
        )
    if report.truncated_lines:
        lines.append(f"Truncated overlong input lines: {report.truncated_lines}")
    if report.dropped_diagnostics:
        lines.append(tr(language, "compiler_dropped").format(count=report.dropped_diagnostics))
    return "\n".join(lines).rstrip() + "\n"
