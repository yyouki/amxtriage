import json

from amxtriage.amxerrors import lookup
from amxtriage.analysis import analyze_logs, build_report
from amxtriage.localization import _MESSAGES, SUPPORTED_LANGUAGES
from amxtriage.parser import parse_frame
from amxtriage.render import (
    format_frame,
    group_title,
    group_to_dict,
    render_error_list,
    render_explain,
    render_json,
    render_markdown,
    render_report,
    render_text,
)
from amxtriage.source import SourceIndex
from helpers import error_block

SECRET = "hunter2-secret"
FORMATS = (render_text, render_markdown, render_json)


def report_from(tmp_path, lines, **options):
    path = tmp_path / "log.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    options.setdefault("top", 20)
    return build_report(analyze_logs([str(path)]), **options)


def sample_report(sample_log, **options):
    options.setdefault("top", 20)
    return build_report(analyze_logs([str(sample_log)]), **options)


def assert_no_control_characters(text):
    for char in text:
        assert char == "\n" or (ord(char) >= 0x20 and ord(char) != 0x7F), repr(char)


def test_text_report_contains_the_key_information(sample_log):
    text = render_text(sample_report(sample_log))
    assert "input  : sample_server_log.txt (56 lines)" in text
    assert "5 distinct problems; 7 event(s) seen in total" in text
    assert "[1] CRASH while executing gamemodes/rp.amx   x1" in text
    assert "[2] RUNTIME ERROR 4: Array index out of bounds   x3" in text
    assert "where  : OnPlayerUpdate  gamemodes/rp.pwn:30 (x2), :31 (x1)" in text
    assert "script : gamemodes/rp.amx" in text
    assert "detail : sscanf" in text
    assert "(more: amxtriage explain 4)" in text


def test_text_report_marks_new_problems_when_a_baseline_is_used(sample_log):
    report = sample_report(sample_log, baseline=frozenset())
    text = render_text(report)
    assert "[1] NEW  CRASH" in text
    assert "5 new problems (0 known problem(s) hidden by baseline)" in text


def test_text_report_for_no_problems_says_so(tmp_path):
    text = render_text(report_from(tmp_path, ["[13:00:00] nothing to see"]))
    assert "no runtime errors, crashes or long callbacks found" in text


def test_text_report_mentions_omitted_problems(sample_log):
    text = render_text(sample_report(sample_log, top=2))
    assert "... 3 more problem(s) not shown (use --top)" in text


def test_missing_file_line_information_points_to_the_debug_flag(tmp_path):
    lines = [
        '[13:46:01] [debug] Run time error 4: "Array index out of bounds"',
        "[13:46:01] [debug] AMX backtrace:",
        "[13:46:01] [debug] #0 000a1b2c in public OnPlayerUpdate (playerid=0) in gamemodes/rp.amx",
    ]
    text = render_text(report_from(tmp_path, lines))
    assert "no file:line information; compile the script with -d3" in text


def test_source_context_marks_the_failing_line(sample_log, sample_sources):
    report = sample_report(
        sample_log, source_index=SourceIndex(str(sample_sources)), context_radius=1
    )
    text = render_text(report)
    assert "> 39 |     new average = total / count;" in text
    assert "  38 |     new count = strval(inputtext);" in text


def test_long_backtraces_and_detail_lists_are_summarised(tmp_path):
    frames = [f"[13:46:01] [debug] #{n} 00000010 in f{n} () at x.pwn:{n + 1}" for n in range(20)]
    names = [f"[13:46:02] [debug]  native_{n}" for n in range(30)]
    lines = [
        '[13:46:01] [debug] Run time error 4: "Array index out of bounds"',
        "[13:46:01] [debug] AMX backtrace:",
        *frames,
        '[13:46:02] [debug] Run time error 19: "File or function is not found"',
        *names,
    ]
    text = render_text(report_from(tmp_path, lines))
    assert "... 8 more frame(s)" in text
    assert "detail : ... 20 more" in text


def test_arguments_are_hidden_by_default_in_every_format(sample_log):
    report = sample_report(sample_log)
    for render in FORMATS:
        output = render(report)
        assert SECRET not in output
        assert "inputtext" not in output
        assert "playerid=3" not in output


def test_arguments_are_shown_only_when_requested(sample_log):
    report = sample_report(sample_log)
    for render in FORMATS:
        output = render(report, show_args=True)
        assert SECRET in output
        assert "playerid=3" in output


def test_format_frame_variants():
    frame = parse_frame(
        "#0 000b00a4 in public OnDialogResponse"
        ' (playerid=3, inputtext[]=@0000a2f0 "x") at gm.pwn:39'
    )
    assert frame is not None
    assert format_frame(frame, False) == "#0 public OnDialogResponse  gm.pwn:39"
    assert format_frame(frame, True).startswith("#0 public OnDialogResponse(playerid=3,")
    native = parse_frame("#1 native SetPlayerName () in samp-server.exe")
    assert native is not None
    assert format_frame(native, False) == "#1 native SetPlayerName  (samp-server.exe)"


def test_group_titles(sample_log):
    groups = sample_report(sample_log).groups
    assert [group_title(group) for group in groups] == [
        "CRASH while executing gamemodes/rp.amx",
        "RUNTIME ERROR 4: Array index out of bounds",
        "RUNTIME ERROR 19: File or function is not found",
        "RUNTIME ERROR 11: Divide by zero",
        "LONG CALLBACK (hang or performance issue)",
    ]


def test_markdown_report_structure(sample_log, sample_sources):
    report = sample_report(
        sample_log, source_index=SourceIndex(str(sample_sources)), context_radius=1
    )
    markdown = render_markdown(report)
    assert markdown.startswith("# amxtriage report\n")
    assert "## 2. `RUNTIME ERROR 4: Array index out of bounds`" in markdown
    assert "- **Count:** 3" in markdown
    assert markdown.count("```text") == markdown.count("```") - markdown.count("```text")
    assert "Native backtrace:" in markdown


def test_markdown_cannot_be_broken_out_of_by_backticks_in_log_content(tmp_path):
    lines = [
        "[13:46:01] [debug] Server crashed while executing evil`](http://x)`.amx",
        "[13:46:01] [debug] AMX backtrace:",
        "[13:46:01] [debug] #0 000a1b2c in public Fo`o (x=1) at a`b.pwn:3",
    ]
    markdown = render_markdown(report_from(tmp_path, lines))
    heading = next(line for line in markdown.splitlines() if line.startswith("## 1."))
    assert heading.count("`") == 2
    assert "evil'](http://x)'.amx" in heading
    fenced = markdown.split("```text")[1].split("```")[0]
    assert "`" not in fenced


def test_json_report_is_valid_and_has_a_stable_shape(sample_log):
    data = json.loads(render_json(sample_report(sample_log)))
    assert data["schema_version"] == 1
    assert data["tool"]["name"] == "amxtriage"
    assert data["summary"]["events"] == 7
    assert data["summary"]["matching_problems"] == 5
    assert data["summary"]["baseline_used"] is False
    problem = data["problems"][1]
    assert set(problem) == {
        "id",
        "kind",
        "code",
        "message",
        "script",
        "function",
        "file",
        "count",
        "lines",
        "first",
        "last",
        "details",
        "backtrace",
        "native_backtrace",
        "causes",
        "source",
        "new",
    }
    assert problem["lines"] == [{"line": 30, "count": 2}, {"line": 31, "count": 1}]
    assert problem["first"] == {
        "source": "sample_server_log.txt",
        "line": 19,
        "timestamp": "13:46:01",
    }
    assert problem["new"] is False
    assert "args" not in problem["backtrace"][0]


def test_json_includes_args_and_new_flag_only_when_applicable(sample_log):
    report = sample_report(sample_log, baseline=frozenset())
    data = json.loads(render_json(report, show_args=True))
    dialog = next(p for p in data["problems"] if p["code"] == 11)
    assert dialog["backtrace"][0]["args"].startswith("playerid=3")
    assert all(problem["new"] is True for problem in data["problems"])


def test_json_includes_source_context_when_available(sample_log, sample_sources):
    report = sample_report(
        sample_log, source_index=SourceIndex(str(sample_sources)), context_radius=1
    )
    data = json.loads(render_json(report))
    crash = data["problems"][0]
    assert crash["source"]["target_line"] == 23
    assert len(crash["source"]["lines"]) == 3


def test_group_to_dict_matches_the_group(sample_log):
    group = sample_report(sample_log).groups[1]
    data = group_to_dict(group)
    assert (data["id"], data["count"], data["code"]) == (group.signature_id, 3, 4)


def test_hostile_log_content_is_sanitized_in_every_format(tmp_path):
    lines = [
        "[1\x1b2] [debug] Server crashed while executing evil\x1b[31m.amx\x1b]0;pwned\x07",
        "[13:46:01] [debug] AMX backtrace:",
        "[13:46:01] [debug] #0 000a1b2c in public Evil\x1b[2J (x=\x1b[1m)"
        " at C:\\\x1b[1mdir\\f\u202e.pwn:3",
        "[13:46:01] [debug] #1 native Nat\x07ive () in mod\x1b.dll",
        "[13:46:01] [debug] Native backtrace:",
        "[13:46:01] [debug] #0 0046b2e7 in ?\x1b? () in samp\x7f.exe",
    ]
    report = report_from(tmp_path, lines)
    for render in FORMATS:
        for show_args in (False, True):
            output = render(report, show_args=show_args)
            assert_no_control_characters(output)
            assert "\u202e" not in output
    json.loads(render_json(report, show_args=True))


def test_locale_catalogs_have_matching_keys_and_placeholders():
    from string import Formatter

    expected_keys = set(_MESSAGES["en"])
    for language in SUPPORTED_LANGUAGES:
        assert set(_MESSAGES[language]) == expected_keys
    expected_fields = {
        key: {field for _, field, _, _ in Formatter().parse(template) if field}
        for key, template in _MESSAGES["en"].items()
    }
    for language in SUPPORTED_LANGUAGES:
        for key, template in _MESSAGES[language].items():
            fields = {field for _, field, _, _ in Formatter().parse(template) if field}
            assert fields == expected_fields[key], (language, key, fields, expected_fields[key])


def test_localized_reports_translate_labels_but_keep_json_schema_stable(sample_log):
    report = sample_report(sample_log)
    indonesian = render_report(report, "text", language="id")
    spanish = render_report(report, "markdown", language="es")
    payload = json.loads(render_report(report, "json", language="id"))

    assert "masukan:" in indonesian
    assert "KESALAHAN RUNTIME 4: Array index out of bounds" in indonesian
    assert "# informe de amxtriage" in spanish
    assert "**Ubicación:**" in spanish
    assert payload["schema_version"] == 1
    assert payload["problems"][1]["kind"] == "runtime_error"


def test_render_report_dispatches_by_format(sample_log):
    report = sample_report(sample_log)
    assert render_report(report, "json").lstrip().startswith("{")
    assert render_report(report, "markdown").startswith("# amxtriage report")
    assert render_report(report, "text").startswith("amxtriage ")


def test_explain_output_for_known_and_guidance_free_codes():
    documented = lookup(4)
    undocumented = lookup(21)
    assert documented is not None
    assert undocumented is not None
    known = render_explain(documented)
    assert known.startswith("AMX error 4: Array index out of bounds")
    assert "Common causes and checks:" in known
    bare = render_explain(undocumented)
    assert "No extra guidance" in bare


def test_localized_explain_and_error_list(sample_log):
    error = lookup(4)
    assert error is not None
    assert render_explain(error, "id").startswith("Error AMX 4: Array index out of bounds")
    assert "Penyebab umum" in render_explain(error, "id")
    assert "Kode error AMX" in render_error_list("id")


def test_error_list_contains_every_code_but_zero():
    listing = render_error_list()
    assert " 4  Array index out of bounds" in listing
    assert "19  File or function is not found" in listing
    assert "28  Wrote to banned address naught" in listing
    assert "(none)" not in listing


def test_error_blocks_helper_produces_parseable_reports(tmp_path):
    report = report_from(tmp_path, error_block(11, "OnPlayerCommandText", message="Divide by zero"))
    assert report.groups[0].function == "OnPlayerCommandText"
