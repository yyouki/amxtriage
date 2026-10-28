from __future__ import annotations

import os
from pathlib import Path

import pytest

from amxtriage.compiler import parse_compiler_lines
from amxtriage.errors import SourceError
from amxtriage.fixes import build_patch_preview, render_patch_preview
from amxtriage.source import SourceIndex


EXPECTED_MESSAGE = 'expected token: ";", but found "return"'


def parse_pawn_diagnostic(
    *,
    file: str = "gamemodes/rp.pwn",
    line: int = 2,
    code: str = "001",
    message: str = EXPECTED_MESSAGE,
    severity: str = "error",
):
    diagnostics, dropped = parse_compiler_lines(
        [f"{file}({line}) : {severity} {code}: {message}"],
        source_language="pawn",
    )
    assert dropped == 0
    assert len(diagnostics) == 1
    return diagnostics[0]


def make_source(root: Path, content: str) -> Path:
    target = root / "gamemodes" / "rp.pwn"
    target.parent.mkdir(parents=True)
    target.write_text(content, encoding="utf-8", newline="")
    return target


def test_patch_preview_emits_one_unified_diff_without_modifying_source(tmp_path: Path) -> None:
    source = make_source(tmp_path, "new value = 42\nreturn 1;\n")
    before = source.read_bytes()
    assert os.path.isfile(source)
    preview = build_patch_preview(
        [parse_pawn_diagnostic()],
        SourceIndex(str(tmp_path)),
    )

    assert preview.status == "ready"
    assert preview.file == "gamemodes/rp.pwn"
    assert preview.line == 2
    assert preview.patch is not None
    assert preview.patch.startswith("--- a/gamemodes/rp.pwn\n")
    assert "+++ b/gamemodes/rp.pwn\n" in preview.patch
    assert "-new value = 42\n" in preview.patch
    assert "+new value = 42;\n" in preview.patch
    assert source.read_bytes() == before


def test_patch_preview_preserves_crlf_and_does_not_rewrite_file(tmp_path: Path) -> None:
    source = tmp_path / "rp.pwn"
    source.write_bytes(b"new value = 42\r\nreturn 1;\r\n")
    before = source.read_bytes()
    preview = build_patch_preview(
        [parse_pawn_diagnostic(file="rp.pwn")],
        SourceIndex(str(tmp_path)),
    )

    assert preview.status == "ready"
    assert preview.patch is not None
    assert "+new value = 42;\r\n" in preview.patch
    assert source.read_bytes() == before


def test_patch_preview_json_is_explicitly_diff_only_and_never_applies_changes(
    tmp_path: Path,
) -> None:
    make_source(tmp_path, "new value = 42\nreturn 1;\n")
    preview = build_patch_preview([parse_pawn_diagnostic()], SourceIndex(str(tmp_path)))
    rendered = render_patch_preview(preview, "json")

    assert '"status": "ready"' in rendered
    assert '"source_modified": false' in rendered
    assert '"compiler_executed": false' in rendered
    assert '"patch": "--- a/gamemodes/rp.pwn' in rendered


def test_no_matching_diagnostic_produces_no_patch(tmp_path: Path) -> None:
    make_source(tmp_path, "new value = 42\nreturn 1;\n")
    diagnostic = parse_pawn_diagnostic(message='undefined symbol "value"')
    preview = build_patch_preview([diagnostic], SourceIndex(str(tmp_path)))

    assert preview.status == "no_candidate"
    assert preview.patch is None
    assert "no source file was modified" in preview.message


def test_multiple_matching_diagnostics_are_refused_as_ambiguous(tmp_path: Path) -> None:
    make_source(tmp_path, "new value = 42\nreturn 1;\nnew other = 3\nreturn 2;\n")
    diagnostics, _ = parse_compiler_lines(
        [
            f'gamemodes/rp.pwn(2) : error 001: {EXPECTED_MESSAGE}',
            f'gamemodes/rp.pwn(4) : error 001: {EXPECTED_MESSAGE}',
        ],
        source_language="pawn",
    )

    preview = build_patch_preview(diagnostics, SourceIndex(str(tmp_path)))
    assert preview.status == "ambiguous"
    assert preview.patch is None


def test_non_simple_previous_line_is_refused(tmp_path: Path) -> None:
    cases = [
        "if (is_ready)\nreturn 1;\n",
        "new value = 42 // comment\nreturn 1;\n",
        "new value =\nreturn 1;\n",
        "new value = 42;\nreturn 1;\n",
        "new value = {1, 2, 3}\nreturn 1;\n",
    ]
    for source_text in cases:
        root = tmp_path / str(cases.index(source_text))
        root.mkdir()
        target = root / "rp.pwn"
        target.write_text(source_text, encoding="utf-8")
        preview = build_patch_preview(
            [parse_pawn_diagnostic(file="rp.pwn")],
            SourceIndex(str(root)),
        )
        assert preview.status == "blocked"
        assert preview.patch is None
        assert target.read_text(encoding="utf-8") == source_text


def test_target_line_must_start_with_return_and_match_indentation(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    source = root / "rp.pwn"
    source.write_text("    new value = 42\nreturn 1;\n", encoding="utf-8")
    preview = build_patch_preview(
        [parse_pawn_diagnostic(file="rp.pwn")],
        SourceIndex(str(root)),
    )
    assert preview.status == "blocked"
    assert preview.patch is None


def test_source_must_resolve_inside_the_configured_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "secret.pwn"
    outside.write_text("new value = 42\nreturn 1;\n", encoding="utf-8")
    preview = build_patch_preview(
        [parse_pawn_diagnostic(file=str(outside))],
        SourceIndex(str(root)),
    )
    assert preview.status == "blocked"
    assert preview.patch is None


def test_non_utf8_source_is_refused_without_rewriting(tmp_path: Path) -> None:
    source = tmp_path / "rp.pwn"
    before = b"new value = caf\xe9\nreturn 1;\n"
    source.write_bytes(before)
    preview = build_patch_preview(
        [parse_pawn_diagnostic(file="rp.pwn")],
        SourceIndex(str(tmp_path)),
    )

    assert preview.status == "blocked"
    assert "not UTF-8" in preview.message
    assert preview.patch is None
    assert source.read_bytes() == before


def test_control_characters_in_diff_context_are_refused(tmp_path: Path) -> None:
    source = tmp_path / "rp.pwn"
    source.write_bytes(b"// \x1b[31m unsafe\nnew value = 42\nreturn 1;\n")
    before = source.read_bytes()
    preview = build_patch_preview(
        [parse_pawn_diagnostic(file="rp.pwn")],
        SourceIndex(str(tmp_path)),
    )

    assert preview.status == "blocked"
    assert preview.patch is None
    assert source.read_bytes() == before

def test_patch_preview_refuses_invalid_source_dir(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="source directory"):
        SourceIndex(str(tmp_path / "missing"))
