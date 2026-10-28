import os
from pathlib import Path

import pytest

from amxtriage.compiler import CompilerDiagnostic, parse_compiler_lines
from amxtriage.errors import SourceError
from amxtriage.fixes import apply_patch_preview, build_patch_preview, render_patch_preview
from amxtriage.source import SourceIndex

EXPECTED_MESSAGE = 'expected token: ";", but found "return"'


def parse_pawn_diagnostic(
    *,
    file: str = "gamemodes/rp.pwn",
    line: int = 2,
    code: str = "001",
    message: str = EXPECTED_MESSAGE,
    severity: str = "error",
) -> CompilerDiagnostic:
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
            f"gamemodes/rp.pwn(2) : error 001: {EXPECTED_MESSAGE}",
            f"gamemodes/rp.pwn(4) : error 001: {EXPECTED_MESSAGE}",
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


def make_fake_test_runner(path: Path, *, mode: str = "success") -> Path:
    runner = path / f"test-runner-{mode}"
    if mode == "success":
        body = "print('synthetic tests passed')\n"
    elif mode == "fail":
        body = "print('synthetic tests failed')\nraise SystemExit(7)\n"
    elif mode == "timeout":
        body = "import time\ntime.sleep(5)\n"
    elif mode == "output":
        body = "print('x' * 300000)\n"
    else:
        raise ValueError("unsupported fake test runner mode")
    runner.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    runner.chmod(0o755)
    return runner


def make_fake_compiler(path: Path) -> Path:
    script = path / "pawncc-stub"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "source = pathlib.Path(args[-1])\n"
        "text = source.read_text(encoding='utf-8')\n"
        "if 'COMPILER_FAIL' in text:\n"
        "    print('synthetic compiler rejection')\n"
        "    raise SystemExit(1)\n"
        "output = next((arg[2:] for arg in args if arg.startswith('-o')), None)\n"
        "if output is None:\n"
        "    print('missing output argument')\n"
        "    raise SystemExit(2)\n"
        "pathlib.Path(output).write_bytes(b'AMX')\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_patch_apply_requires_matching_review_hashes_and_does_not_edit_on_mismatch(
    tmp_path: Path,
) -> None:
    source = make_source(tmp_path, "new value = 42\nreturn 1;\n")
    original = source.read_bytes()
    source_index = SourceIndex(str(tmp_path))
    preview = build_patch_preview([parse_pawn_diagnostic()], source_index)
    compiler = make_fake_compiler(tmp_path)

    result = apply_patch_preview(
        preview,
        source_index,
        expected_patch_sha256="0" * 64,
        expected_source_sha256=preview.source_sha256 or "",
        compiler=str(compiler),
        compile_only=True,
    )

    assert result.status == "confirmation_mismatch"
    assert source.read_bytes() == original
    assert not list(tmp_path.glob("*.amxtriage-backup-*"))


@pytest.mark.skipif(os.name == "nt", reason="executable test compiler uses a POSIX shebang")
def test_patch_apply_creates_checkpoint_and_keeps_patch_only_after_compiler_success(
    tmp_path: Path,
) -> None:
    source = make_source(tmp_path, "new value = 42\nreturn 1;\n")
    original = source.read_bytes()
    source_index = SourceIndex(str(tmp_path))
    preview = build_patch_preview([parse_pawn_diagnostic()], source_index)
    compiler = make_fake_compiler(tmp_path)

    result = apply_patch_preview(
        preview,
        source_index,
        expected_patch_sha256=preview.patch_sha256 or "",
        expected_source_sha256=preview.source_sha256 or "",
        compiler=str(compiler),
        compile_only=True,
    )

    assert result.status == "applied"
    assert result.compiler_exit_code == 0
    assert source.read_bytes() == b"new value = 42;\nreturn 1;\n"
    assert result.backup_file is not None
    backup = tmp_path / result.backup_file
    assert backup.read_bytes() == original
    if os.name == "posix":
        assert backup.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(os.name == "nt", reason="executable test compiler uses a POSIX shebang")
def test_patch_apply_rolls_back_exact_original_bytes_after_compiler_failure(
    tmp_path: Path,
) -> None:
    source = make_source(tmp_path, "new value = 42\nreturn 1;\n// COMPILER_FAIL\n")
    original = source.read_bytes()
    source_index = SourceIndex(str(tmp_path))
    preview = build_patch_preview([parse_pawn_diagnostic()], source_index)
    compiler = make_fake_compiler(tmp_path)

    result = apply_patch_preview(
        preview,
        source_index,
        expected_patch_sha256=preview.patch_sha256 or "",
        expected_source_sha256=preview.source_sha256 or "",
        compiler=str(compiler),
        compile_only=True,
    )

    assert result.status == "compile_failed_rolled_back"
    assert result.compiler_exit_code == 1
    assert source.read_bytes() == original
    assert result.backup_file is not None
    assert (tmp_path / result.backup_file).read_bytes() == original



@pytest.mark.skipif(os.name == "nt", reason="test runner uses a POSIX shebang")
def test_patch_apply_runs_explicit_test_command_and_keeps_patch_when_it_passes(
    tmp_path: Path,
) -> None:
    source = make_source(tmp_path, "new value = 42\nreturn 1;\n")
    original = source.read_bytes()
    source_index = SourceIndex(str(tmp_path))
    preview = build_patch_preview([parse_pawn_diagnostic()], source_index)
    compiler = make_fake_compiler(tmp_path)
    runner = make_fake_test_runner(tmp_path)

    result = apply_patch_preview(
        preview,
        source_index,
        expected_patch_sha256=preview.patch_sha256 or "",
        expected_source_sha256=preview.source_sha256 or "",
        compiler=str(compiler),
        test_command=[str(runner)],
    )

    assert result.status == "applied"
    assert result.compiler_exit_code == 0
    assert result.test_exit_code == 0
    assert "synthetic tests passed" in result.test_output
    assert source.read_bytes() == b"new value = 42;\nreturn 1;\n"
    assert result.backup_file is not None
    assert (tmp_path / result.backup_file).read_bytes() == original


@pytest.mark.skipif(os.name == "nt", reason="test runner uses a POSIX shebang")
@pytest.mark.parametrize(
    ("mode", "timeout", "expected_message"),
    [
        ("fail", 5, "exit code 7"),
        ("timeout", 1, "timed out after 1 seconds"),
        ("output", 5, "output exceeded"),
    ],
)
def test_patch_apply_rolls_back_when_test_command_fails(
    tmp_path: Path,
    mode: str,
    timeout: int,
    expected_message: str,
) -> None:
    source = make_source(tmp_path, "new value = 42\nreturn 1;\n")
    original = source.read_bytes()
    source_index = SourceIndex(str(tmp_path))
    preview = build_patch_preview([parse_pawn_diagnostic()], source_index)
    compiler = make_fake_compiler(tmp_path)
    runner = make_fake_test_runner(tmp_path, mode=mode)

    result = apply_patch_preview(
        preview,
        source_index,
        expected_patch_sha256=preview.patch_sha256 or "",
        expected_source_sha256=preview.source_sha256 or "",
        compiler=str(compiler),
        test_command=[str(runner)],
        timeout_seconds=timeout,
    )

    assert result.status == "test_failed_rolled_back"
    assert expected_message in result.message
    assert source.read_bytes() == original
    assert result.backup_file is not None
    assert (tmp_path / result.backup_file).read_bytes() == original


def test_patch_apply_requires_explicit_test_command_or_compile_only(tmp_path: Path) -> None:
    source = make_source(tmp_path, "new value = 42\nreturn 1;\n")
    source_index = SourceIndex(str(tmp_path))
    preview = build_patch_preview([parse_pawn_diagnostic()], source_index)
    compiler = make_fake_compiler(tmp_path)

    with pytest.raises(ValueError, match="test_command or explicitly select"):
        apply_patch_preview(
            preview,
            source_index,
            expected_patch_sha256=preview.patch_sha256 or "",
            expected_source_sha256=preview.source_sha256 or "",
            compiler=str(compiler),
        )
    assert source.read_text(encoding="utf-8") == "new value = 42\nreturn 1;\n"


@pytest.mark.skipif(os.name == "nt", reason="test runner uses a POSIX shebang")
def test_patch_apply_refuses_test_runner_that_changes_source(tmp_path: Path) -> None:
    source = make_source(tmp_path, "new value = 42\nreturn 1;\n")
    source_index = SourceIndex(str(tmp_path))
    preview = build_patch_preview([parse_pawn_diagnostic()], source_index)
    compiler = make_fake_compiler(tmp_path)
    runner = tmp_path / "test-runner-mutates-source"
    runner.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        "pathlib.Path('gamemodes/rp.pwn').write_text('external edit\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    runner.chmod(0o755)

    result = apply_patch_preview(
        preview,
        source_index,
        expected_patch_sha256=preview.patch_sha256 or "",
        expected_source_sha256=preview.source_sha256 or "",
        compiler=str(compiler),
        test_command=[str(runner)],
    )

    assert result.status == "rollback_blocked"
    assert "changed or obscured the patched source" in result.message
    assert source.read_text(encoding="utf-8") == "external edit\n"
    assert result.backup_file is not None
    assert (tmp_path / result.backup_file).read_bytes() == b"new value = 42\nreturn 1;\n"

def test_patch_apply_refuses_source_that_changed_after_review(tmp_path: Path) -> None:
    source = make_source(tmp_path, "new value = 42\nreturn 1;\n")
    source_index = SourceIndex(str(tmp_path))
    preview = build_patch_preview([parse_pawn_diagnostic()], source_index)
    compiler = make_fake_compiler(tmp_path)
    source.write_bytes(b"new value = 99\nreturn 1;\n")

    with pytest.raises(OSError, match="changed since preview"):
        apply_patch_preview(
            preview,
            source_index,
            expected_patch_sha256=preview.patch_sha256 or "",
            expected_source_sha256=preview.source_sha256 or "",
            compiler=str(compiler),
            compile_only=True,
        )
    assert source.read_bytes() == b"new value = 99\nreturn 1;\n"


def test_patch_preview_exposes_hashes_required_for_opt_in_apply(tmp_path: Path) -> None:
    make_source(tmp_path, "new value = 42\nreturn 1;\n")
    preview = build_patch_preview([parse_pawn_diagnostic()], SourceIndex(str(tmp_path)))
    rendered = render_patch_preview(preview, "json")

    assert preview.source_sha256 is not None
    assert len(preview.source_sha256) == 64
    assert preview.patch_sha256 is not None
    assert len(preview.patch_sha256) == 64
    assert f'"source_sha256": "{preview.source_sha256}"' in rendered
    assert f'"patch_sha256": "{preview.patch_sha256}"' in rendered
