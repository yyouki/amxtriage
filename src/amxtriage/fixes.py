"""Conservative, diff-only source repair proposals.

The first rule is deliberately narrow: suggest a missing semicolon before a Pawn return
only when compiler output is exact and the preceding line is a simple assignment/declaration.
This module never writes or executes source code.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal, Sequence

from amxtriage.compiler import CompilerDiagnostic
from amxtriage.source import SourceIndex
from amxtriage.textutil import sanitize

PatchStatus = Literal["ready", "no_candidate", "ambiguous", "blocked"]
PatchApplyStatus = Literal[
    "applied", "confirmation_mismatch", "compile_failed_rolled_back", "rollback_blocked"
]
MAX_COMPILER_OUTPUT_CHARS = 4000
MAX_COMPILER_TIMEOUT_SECONDS = 120

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
    source_sha256: str | None = None
    patch_sha256: str | None = None
    replacement_bytes: bytes | None = field(default=None, repr=False, compare=False)


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
        source_sha256=hashlib.sha256(raw_source).hexdigest(),
        patch_sha256=hashlib.sha256(patch.encode("utf-8")).hexdigest(),
        replacement_bytes="".join(changed_lines).encode("utf-8"),
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
            "source_sha256": preview.source_sha256,
            "patch_sha256": preview.patch_sha256,
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
    if preview.source_sha256:
        lines.append(f"Source SHA-256: {preview.source_sha256}")
    if preview.patch_sha256:
        lines.append(f"Patch SHA-256: {preview.patch_sha256}")
    if preview.file:
        location = sanitize(preview.file, 500)
        if preview.line is not None:
            location += f":{preview.line}"
        lines.append(f"Location: {location}")
    if preview.patch:
        lines.extend(["", preview.patch.rstrip("\n")])
    return "\n".join(lines) + "\n"


@dataclass(frozen=True, slots=True)
class PatchApplyResult:
    status: PatchApplyStatus
    message: str
    file: str
    backup_file: str | None = None
    compiler_exit_code: int | None = None
    compiler_output: str = ""


def _safe_read_target(path: Path, *, max_bytes: int = 8 * 1024 * 1024) -> tuple[bytes, os.stat_result]:
    """Read one regular, single-link file without following the final symlink."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise OSError("target is not a regular file")
        if before.st_nlink > 1:
            raise OSError("target has multiple hard links")
        if before.st_size > max_bytes:
            raise OSError("target exceeds the source size limit")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            data = handle.read(max_bytes + 1)
        after = os.fstat(descriptor)
        if len(data) > max_bytes:
            raise OSError("target exceeds the source size limit")
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise OSError("target changed while it was being read")
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
            raise OSError("target changed while it was being read")
        path_info = path.stat(follow_symlinks=False)
        if stat.S_ISLNK(path_info.st_mode):
            raise OSError("target became a symbolic link")
        if (path_info.st_dev, path_info.st_ino) != (after.st_dev, after.st_ino):
            raise OSError("target path changed while it was being read")
        return data, after
    finally:
        os.close(descriptor)


def _write_exclusive(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, mode)
    try:
        os.fchmod(descriptor, mode)
        offset = 0
        while offset < len(data):
            written = os.write(descriptor, data[offset:])
            if written <= 0:
                raise OSError("file write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _make_temporary_replacement(target: Path, data: bytes, mode: int) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{target.name}.amxtriage-", suffix=".tmp", dir=target.parent
    )
    temp_path = Path(raw_path)
    try:
        os.fchmod(descriptor, mode)
        offset = 0
        while offset < len(data):
            written = os.write(descriptor, data[offset:])
            if written <= 0:
                raise OSError("temporary file write made no progress")
            offset += written
        os.fsync(descriptor)
    except Exception:
        os.close(descriptor)
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise
    os.close(descriptor)
    return temp_path


def _resolve_compiler_path(compiler: str) -> Path:
    supplied = Path(compiler).expanduser()
    if supplied.is_absolute() or os.sep in compiler or (os.altsep and os.altsep in compiler):
        candidate = supplied.resolve(strict=True)
    else:
        located = shutil.which(compiler)
        if located is None:
            raise OSError("compiler executable was not found")
        candidate = Path(located).resolve(strict=True)
    info = candidate.stat()
    if not stat.S_ISREG(info.st_mode):
        raise OSError("compiler path is not a regular file")
    if os.name != "nt" and not os.access(candidate, os.X_OK):
        raise OSError("compiler file is not executable")
    return candidate


def _temporary_rollback(
    target: Path,
    original: bytes,
    original_mode: int,
    *,
    expected_device: int,
    expected_inode: int,
    expected_replacement_sha256: str,
) -> bool:
    """Restore original bytes only if no external process changed the applied file."""
    try:
        current, info = _safe_read_target(target)
        if (info.st_dev, info.st_ino) != (expected_device, expected_inode):
            return False
        if hashlib.sha256(current).hexdigest() != expected_replacement_sha256:
            return False
        temporary = _make_temporary_replacement(target, original, original_mode)
        latest, latest_info = _safe_read_target(target)
        if (
            (latest_info.st_dev, latest_info.st_ino) != (expected_device, expected_inode)
            or hashlib.sha256(latest).hexdigest() != expected_replacement_sha256
        ):
            temporary.unlink(missing_ok=True)
            return False
        os.replace(temporary, target)
        return True
    except OSError:
        return False


def apply_patch_preview(
    preview: PatchPreview,
    source_index: SourceIndex,
    *,
    expected_patch_sha256: str,
    expected_source_sha256: str,
    compiler: str,
    include_dirs: Sequence[str] = (),
    timeout_seconds: int = 30,
) -> PatchApplyResult:
    """Apply one reviewed preview, compile it, and restore it if validation fails.

    This is intentionally explicit and narrow: callers must supply both hashes copied from a
    prior preview, a trusted Pawn compiler, and any required include paths. Source changes,
    ambiguous locations, hard links, symlinks, and failed compile validation are refused.
    """
    if preview.status != "ready" or not preview.patch or preview.replacement_bytes is None:
        raise ValueError("only a ready patch preview can be applied")
    if not preview.file or not preview.source_sha256 or not preview.patch_sha256:
        raise ValueError("patch preview is missing integrity metadata")
    actual_patch_hash = hashlib.sha256(preview.patch.encode("utf-8")).hexdigest()
    if actual_patch_hash != preview.patch_sha256:
        raise ValueError("patch preview integrity check failed")
    if (
        expected_patch_sha256 != preview.patch_sha256
        or expected_source_sha256 != preview.source_sha256
    ):
        return PatchApplyResult(
            "confirmation_mismatch",
            "The reviewed patch/source hash does not match the current preview. No source was modified.",
            preview.file,
        )
    if not 1 <= timeout_seconds <= MAX_COMPILER_TIMEOUT_SECONDS:
        raise ValueError(f"compiler timeout must be between 1 and {MAX_COMPILER_TIMEOUT_SECONDS} seconds")
    compiler_path = _resolve_compiler_path(compiler)
    resolved_include_dirs: list[Path] = []
    for item in include_dirs:
        directory = Path(item).expanduser().resolve(strict=True)
        if not directory.is_dir():
            raise OSError("an include directory is not a directory")
        resolved_include_dirs.append(directory)

    relative = PurePosixPath(preview.file)
    if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise OSError("the patch path is not a safe relative path")
    root = source_index.root
    target = root.joinpath(*relative.parts)
    try:
        resolved_target = target.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise OSError("the source target no longer exists") from error
    if resolved_target != target or not resolved_target.is_relative_to(root):
        raise OSError("the source target is a symlink or escapes the configured source root")
    for parent in target.parents:
        if parent == root.parent:
            break
        if parent == root:
            continue
        if parent.is_symlink():
            raise OSError("a source directory component is a symlink")
    if not target.exists():
        raise OSError("the source target no longer exists")

    indexed = source_index.read_bytes(preview.file)
    if indexed is None or indexed[0] != preview.file:
        raise OSError("the source path no longer resolves uniquely inside --source-dir")
    original, original_info = _safe_read_target(target)
    source_hash = hashlib.sha256(original).hexdigest()
    if source_hash != preview.source_sha256 or indexed[1] != original:
        raise OSError("the source changed since preview; regenerate and review the patch")
    replacement = preview.replacement_bytes
    replacement_hash = hashlib.sha256(replacement).hexdigest()
    if replacement == original:
        raise OSError("the proposed replacement does not change the source")

    backup = target.with_name(
        f".{target.name}.amxtriage-backup-{source_hash[:12]}-{uuid.uuid4().hex[:8]}"
    )
    _write_exclusive(backup, original, mode=0o600)
    temporary: Path | None = None
    replaced = False
    replacement_info: os.stat_result | None = None
    try:
        temporary = _make_temporary_replacement(
            target, replacement, stat.S_IMODE(original_info.st_mode)
        )
        latest, latest_info = _safe_read_target(target)
        if (
            (latest_info.st_dev, latest_info.st_ino) != (original_info.st_dev, original_info.st_ino)
            or hashlib.sha256(latest).hexdigest() != source_hash
        ):
            raise OSError("the source changed during patch preparation; no patch was applied")
        os.replace(temporary, target)
        temporary = None
        replaced = True
        replacement_info = target.stat(follow_symlinks=False)

        compiler_output = ""
        compiler_exit_code: int | None = None
        try:
            with tempfile.TemporaryDirectory(prefix="amxtriage-compile-") as directory:
                artifact = Path(directory) / "validation.amx"
                command = [
                    str(compiler_path),
                    *(f"-i{item}" for item in resolved_include_dirs),
                    f"-o{artifact}",
                    str(target),
                ]
                completed = subprocess.run(
                    command,
                    cwd=str(root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_seconds,
                    check=False,
                    shell=False,
                )
                compiler_exit_code = completed.returncode
                compiler_output = sanitize(completed.stdout, MAX_COMPILER_OUTPUT_CHARS)
                compile_ok = completed.returncode == 0 and artifact.is_file() and artifact.stat().st_size > 0
                if compile_ok:
                    return PatchApplyResult(
                        "applied",
                        "Patch applied and the configured Pawn compiler produced a non-empty AMX artifact. "
                        "Gameplay behavior still requires regression/staging tests.",
                        preview.file,
                        backup_file=backup.relative_to(root).as_posix(),
                        compiler_exit_code=compiler_exit_code,
                        compiler_output=compiler_output,
                    )
                failure_message = (
                    "Compiler validation failed (non-zero exit or missing/empty AMX artifact)."
                )
        except subprocess.TimeoutExpired as error:
            compiler_exit_code = None
            captured = error.stdout or b""
            compiler_output = sanitize(
                captured.decode("utf-8", errors="replace") if isinstance(captured, bytes) else captured,
                MAX_COMPILER_OUTPUT_CHARS,
            )
            failure_message = f"Compiler validation timed out after {timeout_seconds} seconds."
        except OSError as error:
            failure_message = f"Compiler validation could not run: {error.strerror or type(error).__name__}"

        if replacement_info is None:
            raise OSError("could not verify patched file before rollback")
        restored = _temporary_rollback(
            target,
            original,
            stat.S_IMODE(original_info.st_mode),
            expected_device=replacement_info.st_dev,
            expected_inode=replacement_info.st_ino,
            expected_replacement_sha256=replacement_hash,
        )
        if restored:
            return PatchApplyResult(
                "compile_failed_rolled_back",
                f"{failure_message} Original source restored; backup retained for audit.",
                preview.file,
                backup_file=backup.relative_to(root).as_posix(),
                compiler_exit_code=compiler_exit_code,
                compiler_output=compiler_output,
            )
        return PatchApplyResult(
            "rollback_blocked",
            f"{failure_message} Rollback was blocked because the target changed or could not be safely restored. "
            "Do not overwrite it manually; inspect the source and backup.",
            preview.file,
            backup_file=backup.relative_to(root).as_posix(),
            compiler_exit_code=compiler_exit_code,
            compiler_output=compiler_output,
        )
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass
