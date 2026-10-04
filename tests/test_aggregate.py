from amxtriage.aggregate import (
    MAX_LINE_BUCKETS,
    SIGNATURE_ID_LENGTH,
    Aggregator,
    canonical_signature,
    signature_id,
)
from helpers import error_block, events_of


def add_all(aggregator, lines, source="log.txt"):
    results = []
    for event in events_of(lines):
        results.append(aggregator.add(event, source))
    return results


def test_signature_values_are_locked_for_baseline_compatibility():
    event = events_of(error_block(4, "OnPlayerUpdate", "gamemodes/rp.pwn", 30))[0]
    canonical = canonical_signature(event)
    assert canonical == "v1|runtime_error|4|OnPlayerUpdate|rp.pwn||"
    assert signature_id(canonical) == "67683d049c59"


def test_signature_id_has_the_documented_length_and_alphabet():
    identifier = signature_id("anything")
    assert len(identifier) == SIGNATURE_ID_LENGTH
    assert set(identifier) <= set("0123456789abcdef")


def test_message_wording_does_not_change_the_signature():
    first = events_of(error_block(19, "A", message="File or function is not found"))[0]
    second = events_of(error_block(19, "A", message="File or function is not present"))[0]
    assert canonical_signature(first) == canonical_signature(second)


def test_same_function_on_different_lines_is_one_group_with_line_counts():
    aggregator = Aggregator()
    for line in (30, 30, 31):
        add_all(aggregator, error_block(line=line))
    groups = aggregator.sorted_groups()
    assert len(groups) == 1
    assert groups[0].count == 3
    assert groups[0].line_counts == {30: 2, 31: 1}
    assert groups[0].top_lines(1) == [(30, 2)]


def test_windows_and_linux_paths_to_the_same_file_share_a_signature():
    windows = events_of(error_block(file="C:\\samp\\gamemodes\\rp.pwn"))[0]
    linux = events_of(error_block(file="/srv/samp/gamemodes/rp.pwn"))[0]
    assert canonical_signature(windows) == canonical_signature(linux)


def test_different_functions_or_codes_are_different_groups():
    aggregator = Aggregator()
    add_all(aggregator, error_block(4, "A"))
    add_all(aggregator, error_block(4, "B"))
    add_all(aggregator, error_block(11, "A", message="Divide by zero"))
    assert len(aggregator) == 3


def test_crash_without_amx_frames_is_grouped_by_native_module():
    def crash(module):
        return [
            "[debug] Server crashed while executing gamemodes/rp.amx",
            "[debug] Native backtrace:",
            f"[debug] #0 0046b2e7 in ?? () in {module}",
        ]

    aggregator = Aggregator()
    add_all(aggregator, crash("plugins/mysql.dll"))
    add_all(aggregator, crash("plugins\\mysql.dll"))
    add_all(aggregator, crash("plugins/streamer.dll"))
    assert sorted(group.count for group in aggregator.sorted_groups()) == [1, 2]


def test_missing_native_lists_without_backtrace_are_grouped_by_their_names():
    def missing(*names):
        return [
            '[debug] Run time error 19: "File or function is not found"',
            *[f"[debug]  {name}" for name in names],
        ]

    aggregator = Aggregator()
    add_all(aggregator, missing("sscanf", "mysql_connect"))
    add_all(aggregator, missing("mysql_connect", "sscanf"))
    add_all(aggregator, missing("streamer_tick"))
    assert sorted(group.count for group in aggregator.sorted_groups()) == [1, 2]


def test_group_limit_drops_new_signatures_but_keeps_counting_known_ones():
    aggregator = Aggregator(max_groups=2)
    for name in ("A", "B", "C", "D"):
        add_all(aggregator, error_block(4, name))
    add_all(aggregator, error_block(4, "A"))
    assert len(aggregator) == 2
    assert aggregator.dropped_events == 2
    assert aggregator.total_events == 5
    counts = {group.function: group.count for group in aggregator.sorted_groups()}
    assert counts == {"A": 2, "B": 1}


def test_interrupt_events_are_counted_but_not_grouped():
    aggregator = Aggregator()
    results = add_all(
        aggregator,
        [
            "[debug] Server received interrupt signal",
            "[debug] AMX backtrace:",
            "[debug] #0 00000010 in public A () at x.pwn:1",
        ],
    )
    assert results[0].group is None
    assert aggregator.ignored_interrupts == 1
    assert aggregator.total_events == 0
    assert len(aggregator) == 0


def test_add_reports_whether_the_group_was_created():
    aggregator = Aggregator()
    first = add_all(aggregator, error_block())[0]
    second = add_all(aggregator, error_block())[0]
    assert first.created is True
    assert second.created is False
    assert first.group is second.group


def test_groups_are_ordered_by_kind_then_by_count():
    aggregator = Aggregator()
    add_all(aggregator, ["[debug] Long callback execution detected (hang or performance issue)"])
    for _ in range(5):
        add_all(aggregator, error_block(4, "Frequent"))
    add_all(aggregator, error_block(11, "Rare", message="Divide by zero"))
    add_all(aggregator, ["[debug] Server crashed due to an unknown error"])
    ordered = [(group.kind, group.count) for group in aggregator.sorted_groups()]
    assert ordered == [("crash", 1), ("runtime_error", 5), ("runtime_error", 1), ("long_call", 1)]


def test_first_and_last_occurrences_track_source_line_and_timestamp():
    aggregator = Aggregator()
    add_all(aggregator, error_block(stamp="10:00:00"), source="a.log")
    add_all(aggregator, error_block(stamp="11:30:00"), source="b.log")
    group = aggregator.sorted_groups()[0]
    assert (group.first.source, group.first.timestamp) == ("a.log", "10:00:00")
    assert (group.last.source, group.last.timestamp) == ("b.log", "11:30:00")


def test_distinct_line_buckets_are_bounded():
    aggregator = Aggregator()
    for line in range(1, MAX_LINE_BUCKETS + 50):
        add_all(aggregator, error_block(line=line))
    group = aggregator.sorted_groups()[0]
    assert group.count == MAX_LINE_BUCKETS + 49
    assert len(group.line_counts) == MAX_LINE_BUCKETS
