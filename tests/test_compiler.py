from __future__ import annotations

import json

from amxtriage.cli import main
from amxtriage.compiler import (
    CompilerReport,
    analyze_compiler_outputs,
    parse_compiler_lines,
    render_compiler_report,
)


def test_pawn_compiler_output_keeps_location_and_rule_hint():
    lines = [
        'gamemodes/rp.pwn(42) : error 017: undefined symbol "PlayerData"',
        "gamemodes/rp.pwn(43) : warning 202: number of arguments does not match definition",
    ]
    diagnostics, dropped = parse_compiler_lines(lines, source_language="auto")
    assert dropped == 0
    assert len(diagnostics) == 2
    first = diagnostics[0]
    assert (first.source_language, first.file, first.line, first.code) == (
        "pawn",
        "gamemodes/rp.pwn",
        42,
        "017",
    )
    assert first.severity == "error"
    assert first.hint_key == "compiler_hint_undefined"
    assert diagnostics[1].severity == "warning"


def test_typescript_and_csharp_formats_are_recognized():
    lines = [
        "src/main.ts(12,3): error TS2322: Type string is not assignable to type number.",
        r"C:\src\Main.cs(7,11): error CS1002: expected semicolon",
    ]
    diagnostics, _ = parse_compiler_lines(lines, source_language="auto")
    assert [(d.source_language, d.line, d.column, d.code) for d in diagnostics] == [
        ("typescript", 12, 3, "TS2322"),
        ("csharp", 7, 11, "CS1002"),
    ]


def test_python_traceback_uses_the_innermost_frame():
    lines = [
        "Traceback (most recent call last):",
        '  File "app.py", line 10, in wrapper',
        '  File "src/game.py", line 24, in update',
        "    missing_name()",
        "NameError: name missing_name is not defined",
    ]
    diagnostics, _ = parse_compiler_lines(lines, source_language="auto")
    assert len(diagnostics) == 1
    assert diagnostics[0].source_language == "python"
    assert diagnostics[0].file == "src/game.py"
    assert diagnostics[0].line == 24
    assert diagnostics[0].code == "NameError"


def test_rust_and_go_output_are_recognized():
    rust = [
        "error[E0382]: use of moved value",
        "  --> src/main.rs:5:9",
    ]
    go = ["./cmd/server/main.go:19:8: cannot use value as int value"]
    rust_diagnostics, _ = parse_compiler_lines(rust, source_language="auto")
    go_diagnostics, _ = parse_compiler_lines(go, source_language="auto")
    assert (rust_diagnostics[0].source_language, rust_diagnostics[0].code) == ("rust", "E0382")
    assert (rust_diagnostics[0].line, rust_diagnostics[0].column) == (5, 9)
    assert (go_diagnostics[0].source_language, go_diagnostics[0].line) == ("go", 19)


def test_cpp_and_java_output_are_recognized():
    lines = [
        "src/main.cpp:8:4: error: expected semicolon after expression",
        "src/App.java:15: error: cannot find symbol",
    ]
    diagnostics, _ = parse_compiler_lines(lines, source_language="auto")
    assert [(d.source_language, d.line) for d in diagnostics] == [("c_cpp", 8), ("java", 15)]


def test_eslint_multiline_output_is_recognized():
    lines = [
        "src/client.js",
        "  14:3  warning  Unexpected console statement  no-console",
    ]
    diagnostics, _ = parse_compiler_lines(lines, source_language="auto")
    assert len(diagnostics) == 1
    assert diagnostics[0].source_language == "javascript"
    assert diagnostics[0].line == 14
    assert diagnostics[0].column == 3
    assert diagnostics[0].severity == "warning"


def test_compiler_report_json_schema_is_stable():
    diagnostics, dropped = parse_compiler_lines(
        ['game.pwn(12) : error 017: undefined symbol "pname"'],
        source_language="pawn",
    )
    report = CompilerReport(["compiler.txt"], "pawn", 1, 0, diagnostics, dropped)
    payload = json.loads(render_compiler_report(report, "json", language="id"))
    assert payload["schema_version"] == 1
    assert payload["mode"] == "compiler-diagnostics"
    assert payload["diagnostic_count"] == 1
    assert payload["diagnostics"][0]["file"] == "game.pwn"
    assert payload["diagnostics"][0]["line"] == 12
    assert payload["diagnostics"][0]["hint"].startswith("Periksa ejaan")


def test_input_file_and_cli_integration(tmp_path, capsys):
    source = tmp_path / "compile.txt"
    source.write_text("src/main.ts(3,1): error TS1005: expected semicolon\n", encoding="utf-8")
    report = analyze_compiler_outputs([str(source)], source_language="auto")
    assert report.lines_read == 1
    assert report.diagnostics[0].source_language == "typescript"

    code = main(["diagnose", str(source), "--language", "id", "--format", "text"])
    output = capsys.readouterr().out
    assert code == 0
    assert "diagnostik compiler" in output.lower()
    assert "Baris" in output or "Kode" in output


def test_unrecognized_output_is_not_reported_as_success():
    diagnostics, dropped = parse_compiler_lines(
        ["building project...", "done"], source_language="auto"
    )
    assert diagnostics == []
    assert dropped == 0


def test_diagnostic_limit_bounds_memory():
    lines = [f"src/main.cpp:{line}:4: error: bad expression" for line in range(1, 10)]
    diagnostics, dropped = parse_compiler_lines(lines, source_language="c_cpp", limit=3)
    assert len(diagnostics) == 3
    assert dropped == 6
