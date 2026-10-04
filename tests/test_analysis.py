from amxtriage.analysis import analyze_logs, build_report
from amxtriage.source import SourceIndex
from helpers import error_block


def write_log(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def test_sample_log_totals(sample_log):
    result = analyze_logs([str(sample_log)])
    assert result.lines_read == 56
    assert result.sources == ["sample_server_log.txt"]
    assert result.aggregator.total_events == 7
    assert result.aggregator.ignored_interrupts == 1
    assert len(result.aggregator) == 5


def test_report_orders_crash_first_then_errors_by_count(sample_log):
    report = build_report(analyze_logs([str(sample_log)]), top=20)
    summary = [(group.kind, group.code, group.count) for group in report.groups]
    assert summary == [
        ("crash", None, 1),
        ("runtime_error", 4, 3),
        ("runtime_error", 19, 1),
        ("runtime_error", 11, 1),
        ("long_call", None, 1),
    ]
    assert report.matching_groups == 5
    assert report.omitted_groups == 0


def test_top_limits_displayed_groups_but_not_the_match_count(sample_log):
    report = build_report(analyze_logs([str(sample_log)]), top=2)
    assert len(report.groups) == 2
    assert report.matching_groups == 5
    assert report.omitted_groups == 3


def test_min_count_hides_rare_problems(sample_log):
    report = build_report(analyze_logs([str(sample_log)]), top=20, min_count=2)
    assert [(group.code, group.count) for group in report.groups] == [(4, 3)]


def test_kind_filter_selects_only_requested_kinds(sample_log):
    report = build_report(analyze_logs([str(sample_log)]), top=20, kinds=["crash", "long_call"])
    assert [group.kind for group in report.groups] == ["crash", "long_call"]


def test_baseline_hides_known_problems_and_reports_the_rest(sample_log):
    result = analyze_logs([str(sample_log)])
    everything = result.aggregator.sorted_groups()
    known = frozenset(group.signature_id for group in everything if group.kind != "crash")
    report = build_report(result, top=20, baseline=known)
    assert [group.kind for group in report.groups] == ["crash"]
    assert report.known_hidden == 4
    assert report.baseline_used is True
    assert report.matching_groups == 1


def test_baseline_covering_everything_leaves_nothing(sample_log):
    result = analyze_logs([str(sample_log)])
    known = frozenset(group.signature_id for group in result.aggregator.sorted_groups())
    report = build_report(result, top=20, baseline=known)
    assert report.groups == []
    assert report.matching_groups == 0
    assert report.known_hidden == 5


def test_multiple_files_are_aggregated_in_order(sample_log, tmp_path):
    second = write_log(tmp_path / "server_log.txt", error_block(4, "OnPlayerUpdate", line=30))
    result = analyze_logs([str(sample_log), second])
    group = next(g for g in result.aggregator.sorted_groups() if g.code == 4)
    assert group.count == 4
    assert group.first.source == "sample_server_log.txt"
    assert group.last.source == "server_log.txt"
    assert result.sources == ["sample_server_log.txt", "server_log.txt"]


def test_block_pending_at_end_of_file_is_not_lost(tmp_path):
    path = tmp_path / "log.txt"
    path.write_text('[13:46:01] [debug] Run time error 4: "Array index out of bounds"\n')
    result = analyze_logs([str(path)])
    assert result.aggregator.total_events == 1


def test_block_does_not_leak_across_file_boundaries(tmp_path):
    first = tmp_path / "a.log"
    second = tmp_path / "b.log"
    first.write_text('[13:46:01] [debug] Run time error 4: "Array index out of bounds"\n')
    second.write_text(
        "[13:46:02] [debug] AMX backtrace:\n[13:46:02] [debug] #0 00000010 in f () at x.pwn:1\n"
    )
    result = analyze_logs([str(first), str(second)])
    group = result.aggregator.sorted_groups()[0]
    assert group.sample.frames == ()


def test_empty_log_yields_an_empty_report(tmp_path):
    path = tmp_path / "empty.log"
    path.write_bytes(b"")
    report = build_report(analyze_logs([str(path)]), top=20)
    assert report.groups == []
    assert report.lines_read == 0
    assert report.total_events == 0


def test_truncated_lines_are_reported_in_notes(tmp_path):
    path = tmp_path / "log.txt"
    path.write_bytes(b"x" * 20000 + b"\n" + b"normal\n")
    report = build_report(analyze_logs([str(path)]), top=20)
    assert report.truncated_lines == 1
    assert any("truncated" in note for note in report.notes)


def test_missing_backtrace_note_is_shown_when_no_function_names_exist(tmp_path):
    lines = [
        '[13:46:01] Script[gamemodes/rp.amx]: Run time error 4: "Array index out of bounds"'
    ] * 3
    path = write_log(tmp_path / "plain.log", lines)
    report = build_report(analyze_logs([path]), top=20)
    assert [group.count for group in report.groups] == [3]
    assert any("crashdetect" in note for note in report.notes)


def test_missing_backtrace_note_is_absent_when_function_names_exist(sample_log):
    report = build_report(analyze_logs([str(sample_log)]), top=20)
    assert not any("crashdetect" in note for note in report.notes)


def test_interrupts_are_mentioned_in_notes(sample_log):
    report = build_report(analyze_logs([str(sample_log)]), top=20)
    assert any("interrupt" in note for note in report.notes)


def test_group_limit_is_mentioned_in_notes(tmp_path):
    lines = [line for name in "ABCDE" for line in error_block(4, name)]
    result = analyze_logs([write_log(tmp_path / "many.log", lines)], max_groups=3)
    report = build_report(result, top=20)
    assert report.dropped_events == 2
    assert any("Group limit" in note for note in report.notes)


def test_source_context_is_attached_to_groups_with_a_known_file(sample_log, sample_sources):
    result = analyze_logs([str(sample_log)])
    index = SourceIndex(str(sample_sources))
    report = build_report(result, top=20, source_index=index, context_radius=2)
    assert len(report.contexts) == 4
    crash = report.groups[0]
    snippet = report.contexts[crash.signature_id]
    assert snippet.target_line == 23
    assert "SetPlayerName" in snippet.lines[snippet.target_line - snippet.first_line]


def test_context_radius_zero_disables_source_context(sample_log, sample_sources):
    result = analyze_logs([str(sample_log)])
    report = build_report(
        result, top=20, source_index=SourceIndex(str(sample_sources)), context_radius=0
    )
    assert report.contexts == {}


def test_note_explains_when_no_source_file_matches(sample_log, tmp_path):
    (tmp_path / "unrelated.pwn").write_text("new x;\n")
    result = analyze_logs([str(sample_log)])
    report = build_report(result, top=20, source_index=SourceIndex(str(tmp_path)), context_radius=3)
    assert report.contexts == {}
    assert any("source context" in note for note in report.notes)
