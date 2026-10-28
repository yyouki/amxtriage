"""Exercise the reviewed patch workflow against the pinned real Pawn compiler in CI.

This is an isolated smoke test: it creates a temporary broken Pawn source, captures the compiler's
actual diagnostic, previews a diff, explicitly applies the reviewed hashes, and verifies that the
same compiler accepts the patched file. It never edits repository source files.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path


def run_command(args: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def fail(message: str, *, detail: str = "") -> None:
    if detail:
        print(detail, file=sys.stderr)
    raise SystemExit(message)


def main() -> int:
    if len(sys.argv) != 2:
        fail("usage: validate_patch_with_pawn_compiler.py PAWNCC")
    compiler = Path(sys.argv[1]).resolve(strict=True)

    with tempfile.TemporaryDirectory(prefix="amxtriage-real-patch-") as raw_temp:
        workspace = Path(raw_temp)
        source_root = workspace / "source"
        source_file = source_root / "gamemodes" / "rp.pwn"
        source_file.parent.mkdir(parents=True)
        original = "main()\n{\n    new value = 42\n    return 1;\n}\n"
        source_file.write_text(original, encoding="utf-8")
        original_bytes = source_file.read_bytes()

        broken_compile = run_command(
            [str(compiler), f"-o{workspace / 'before.amx'}", str(source_file)],
            cwd=workspace,
        )
        compiler_log_text = broken_compile.stdout + broken_compile.stderr
        if broken_compile.returncode == 0 or "error 001" not in compiler_log_text:
            fail(
                "Pinned Pawn compiler did not produce the expected missing-semicolon error.",
                detail=compiler_log_text,
            )
        compiler_log = workspace / "compiler.log"
        compiler_log.write_text(compiler_log_text, encoding="utf-8")

        preview_result = run_command(
            [
                sys.executable,
                "-m",
                "amxtriage",
                "patch-preview",
                str(compiler_log),
                "--source-dir",
                str(source_root),
                "--format",
                "json",
            ],
            cwd=workspace,
        )
        if preview_result.returncode != 0:
            fail("amxtriage patch-preview failed on real compiler output.", detail=preview_result.stdout + preview_result.stderr)
        try:
            preview = json.loads(preview_result.stdout)
        except json.JSONDecodeError:
            fail("patch-preview did not return valid JSON.", detail=preview_result.stdout)
        if preview.get("status") != "ready":
            fail("patch-preview did not produce the expected conservative patch.", detail=preview_result.stdout)
        if preview.get("source_modified") is not False or source_file.read_bytes() != original_bytes:
            fail("patch-preview modified the source file; diff-only contract was violated.")
        patch_hash = preview.get("patch_sha256")
        source_hash = preview.get("source_sha256")
        if not isinstance(patch_hash, str) or not isinstance(source_hash, str):
            fail("patch-preview omitted the hashes required for explicit apply.")

        apply_result = run_command(
            [
                sys.executable,
                "-m",
                "amxtriage",
                "patch-apply",
                str(compiler_log),
                "--source-dir",
                str(source_root),
                "--compiler",
                str(compiler),
                "--compile-only",
                "--confirm-patch-sha256",
                patch_hash,
                "--confirm-source-sha256",
                source_hash,
            ],
            cwd=workspace,
        )
        apply_output = apply_result.stdout + apply_result.stderr
        if apply_result.returncode != 0 or "Apply status: applied" not in apply_output:
            fail("patch-apply failed with the real Pawn compiler.", detail=apply_output)
        expected = "    new value = 42;\n"
        if expected not in source_file.read_text(encoding="utf-8"):
            fail("patch-apply did not add the expected semicolon.", detail=source_file.read_text(encoding="utf-8"))

        print("Real Pawn compiler patch smoke test passed: preview was non-mutating; reviewed apply compiled.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
