"""Conservative, diff-only source repair proposals.

The first rule is deliberately narrow: suggest a missing semicolon before a Pawn return
only when compiler output is exact and the preceding line is a simple assignment/declaration.
This module never writes or executes source code.
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from amxtriage.compiler import CompilerDiagnostic
from amxtriage.source import SourceIndex
from amxtriage.textutil import sanitize

PatchStatus = Literal["ready", "no_candidate", "ambiguous", "blocked"]

_MISSING_SEMICOLON_BEFORE_RETURN = re.compile(
    r'^expected token:\s*";"\s*,\s*but found\s*"return"\s*$',
    re.IGNORECASE,
)
_SIMPLE_ASSIGNMENT = re.compile(r"(?<![=!<>])=(?!=)")
_BLOCKED_START = re.compile(
    r"^(?:#|//|/\*|\*|if\b|else\b|for\b|while\b|switch\b|case\b|default\b|"
    r"do\b|return\b|break\b|continue\b|goto\b|public\b|stock\b|forward\b|"
    r"native\b|static\b|enum\b|struct\b)",
    re.IGNORECASE,
)
_BAD_TRAILING_TOKENS = (
    "=",
    "+",
    "-",
    "*",
    "/",
    "%",
    "&",
    "|",
    ".",
    ",",
    ":",
    "?",
    "(",
    "[",
    "\\",
    "<",
    ">",
)


@dataclass(frozen=True, slots=True)
class PatchPreview:
    status: PatchStatus
    message: str
    diagnostic_count: int
    candidate_count: int
    file: str | None = None
    line: int | None = None
    diagnostic_id: str | None = None
    patch: str | None = None


def _is_target_diagnostic(diagnostic: CompilerDiagnostic) -> bool:
    return (
        diagnostic.source_language == "pawn"
        and diagnostic.severity in {"error", "fatal error"}
        and diagnostic.code == "001"
        and _MISSING_SEMICOLON_BEFORE_RETURN.fullmatch(diagnostic.message.strip()) is not None
    )


def _line_parts(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith(("\n", "\r")):
        return line[:-1], line[-1:]
    return line, ""


def _simple_assignment(line: str) -> bool:
    statement = line.strip()
    if not statement or statement.endswith(";") or _BLOCKED_START.match(statement):
        return False
    if any(token in statement for token in (";", "//", "/*", "*/", "{", "}")):
        return False
    if any(statement.endswith(token) for token in _BAD_TRAILING_TOKENS):
        return False
    if "," in statement or "?" in statement or ":" in statement:
        return False
    if statement.count("(") != statement.count(")") or statement.count("[") != statement.count("]"):
        return False
    return len(_SIMPLE_ASSIGNMENT.findall(statement)) == 1


def _has_unsafe_controls(text: str) -> bool:
    for character in text:
        category = unicodedata.category(character)
        if character != "\t" and category in {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"}:
            return True
    return False


def build_patch_preview(
    diagnostics: list[CompilerDiagnostic] | tuple[CompilerDiagnostic, ...],
    source_index: SourceIndex,
) -> PatchPreview:
    """Propose a single reviewable Pawn semicolon diff; never modify the source tree."""
    targets = [diagnostic for diagnostic in diagnostics if _is_target_diagnostic(diagnostic)]
    if not targets:
        return PatchPreview(
            "no_candidate",
            "No supported high-confidence fix candidate was found; no source file was modified.",
            len(diagnostics),
            0,
        )
    if len(targets) != 1:
        return PatchPreview(
            "ambiguous",
            "Multiple matching diagnostics were found; review them individually. "
            "No patch was generated.",
            len(diagnostics),
            len(targets),
        )

    diagnostic = targets[0]
    if not diagnostic.file or diagnostic.line is None or diagnostic.line < 2:
        return PatchPreview(
            "blocked",
            "The diagnostic does not contain a usable source file and line; "
            "no patch was generated.",
            len(diagnostics),
            1,
            diagnostic_id=diagnostic.diagnostic_id,
        )
    if not diagnostic.file.lower().endswith((".pwn", ".inc", ".p", ".pawn")):
        return PatchPreview(
            "blocked",
            "The diagnostic file is not a supported Pawn source file; no patch was generated.",
            len(diagnostics),
            1,
            diagnostic_id=diagnostic.diagnostic_id,
        )

    source = source_index.read_bytes(diagnostic.file)
    if source is None:
        return PatchPreview(
            "blocked",
            "The source file could not be resolved uniquely and safely inside --source-dir; "
            "no patch was generated.",
            len(diagnostics),
            1,
            diagnostic_id=diagnostic.diagnostic_id,
        )
    relative_path, raw_source = source
    if (
        _has_unsafe_controls(relative_path)
        or relative_path.startswith("/")
        or ".." in relative_path.split("/")
    ):
        return PatchPreview(
            "blocked",
            "The resolved source path cannot be represented safely in a patch; "
            "no patch was generated.",
            len(diagnostics),
            1,
            diagnostic_id=diagnostic.diagnostic_id,
        )
    try:
        original_text = raw_source.decode("utf-8")
    except UnicodeDecodeError:
        return PatchPreview(
            "blocked",
            "The source file is not UTF-8; the preview refuses to risk changing its encoding.",
            len(diagnostics),
            1,
            file=relative_path,
            line=diagnostic.line,
            diagnostic_id=diagnostic.diagnostic_id,
        )

    original_lines = original_text.splitlines(keepends=True)
    target_index = diagnostic.line - 1
    previous_index = target_index - 1
    if target_index >= len(original_lines):
        return PatchPreview(
            "blocked",
            "The reported line is outside the source file; no patch was generated.",
            len(diagnostics),
            1,
            file=relative_path,
            line=diagnostic.line,
            diagnostic_id=diagnostic.diagnostic_id,
        )

    current_text, _ = _line_parts(original_lines[target_index])
    previous_text, previous_ending = _line_parts(original_lines[previous_index])
    if re.match(r"^\s*return(?:\s|;|$)", current_text) is None:
        return PatchPreview(
            "blocked",
            "The reported line does not begin with a Pawn return statement; "
            "no patch was generated.",
            len(diagnostics),
            1,
            file=relative_path,
            line=diagnostic.line,
            diagnostic_id=diagnostic.diagnostic_id,
        )
    if len(previous_text) - len(previous_text.lstrip(" \t")) != len(current_text) - len(
        current_text.lstrip(" \t")
    ):
        return PatchPreview(
            "blocked",
            "The preceding statement has different indentation; no patch was generated.",
            len(diagnostics),
            1,
            file=relative_path,
            line=diagnostic.line,
            diagnostic_id=diagnostic.diagnostic_id,
        )
    if not _simple_assignment(previous_text):
        return PatchPreview(
            "blocked",
            "The preceding line is not a single unambiguous assignment/declaration; "
            "no patch was generated.",
            len(diagnostics),
            1,
            file=relative_path,
            line=diagnostic.line,
            diagnostic_id=diagnostic.diagnostic_id,
        )

    context_start = max(0, previous_index - 3)
    context_end = min(len(original_lines), previous_index + 4)
    if any(
        _has_unsafe_controls(_line_parts(original_lines[index])[0])
        for index in range(context_start, context_end)
    ):
        return PatchPreview(
            "blocked",
            "The source context contains control/format characters; no patch was generated.",
            len(diagnostics),
            1,
            file=relative_path,
            line=diagnostic.line,
            diagnostic_id=diagnostic.diagnostic_id,
        )

    changed_lines = list(original_lines)
    changed_lines[previous_index] = previous_text + ";" + previous_ending
    patch = "".join(
        difflib.unified_diff(
            original_lines,
            changed_lines,
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            n=3,
        )
    )
    if not patch:
        return PatchPreview(
            "blocked",
            "The proposed change produced no diff; no source file was modified.",
            len(diagnostics),
            1,
            file=relative_path,
            line=diagnostic.line,
            diagnostic_id=diagnostic.diagnostic_id,
        )

    return PatchPreview(
        "ready",
        "One conservative patch is available for review. Source files were not modified "
        "and no compiler was run.",
        len(diagnostics),
        1,
        file=relative_path,
        line=diagnostic.line,
        diagnostic_id=diagnostic.diagnostic_id,
        patch=patch,
    )


def render_patch_preview(preview: PatchPreview, output_format: str = "text") -> str:
    """Render a preview as human text, JSON, or a patch-only unified diff."""
    if output_format == "unified":
        return preview.patch or ""
    if output_format == "json":
        payload: dict[str, object] = {
            "schema_version": 1,
            "tool": "amxtriage",
            "mode": "patch-preview",
            "status": preview.status,
            "message": preview.message,
            "diagnostic_count": preview.diagnostic_count,
            "candidate_count": preview.candidate_count,
            "source": {"file": preview.file, "line": preview.line},
            "diagnostic_id": preview.diagnostic_id,
            "patch": preview.patch,
            "source_modified": False,
            "compiler_executed": False,
        }
        return json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"

    lines = [
        f"Patch preview: {preview.status}",
        preview.message,
        "Source modified: no",
        "Compiler executed: no",
    ]
    if preview.file:
        location = sanitize(preview.file, 500)
        if preview.line is not None:
            location += f":{preview.line}"
        lines.append(f"Location: {location}")
    if preview.patch:
        lines.extend(["", preview.patch.rstrip("\n")])
    return "\n".join(lines) + "\n"
