import pytest

from amxtriage.parser import (
    MAX_DETAILS,
    MAX_FRAMES,
    MAX_NAME_DETAILS,
    LogParser,
    parse_frame,
    parse_lines,
    parse_native_frame,
    split_prefix,
)

STAMP = "[13:46:01]"


def events_of(lines):
    return list(parse_lines(lines))


@pytest.mark.parametrize(
    ("line", "timestamp", "tags", "body"),
    [
        ("[13:46:01] [debug] Run time error", "13:46:01", ("debug",), "Run time error"),
        ("[debug] Run time error", None, ("debug",), "Run time error"),
        ("[13:46:01] Script[a.amx]: x", "13:46:01", (), "Script[a.amx]: x"),
        (
            "[2026-10-01T14:29:46+0000] [Info] [debug] Run time error",
            "2026-10-01T14:29:46+0000",
            ("info", "debug"),
            "Run time error",
        ),
        ("[13:46:01] [chat] [0]Alice: hi", "13:46:01", ("chat",), "[0]Alice: hi"),
        ("[chat] [0]Alice: hi", None, ("chat",), "[0]Alice: hi"),
        ("plain line", None, (), "plain line"),
        ("", None, (), ""),
        ("[13:46:01]  detail", "13:46:01", (), " detail"),
        ("[13:46:01] [debug]  detail", "13:46:01", ("debug",), " detail"),
    ],
)
def test_split_prefix(line, timestamp, tags, body):
    prefix = split_prefix(line)
    assert (prefix.timestamp, prefix.tags, prefix.body) == (timestamp, tags, body)


def test_split_prefix_limits_the_number_of_tags():
    prefix = split_prefix("[a] [b] [c] [d] [e] body")
    assert prefix.tags == ("a", "b", "c")
    assert prefix.body.startswith("[d]")


FRAME_CASES = [
    (
        "#0 000000d8 in public out_of_bounds_pos () at C:\\work\\tests\\bounds.pwn:29",
        ("amx", "out_of_bounds_pos", True, "C:\\work\\tests\\bounds.pwn", 29, None, ""),
    ),
    (
        "#1 native CallLocalFunction () in plugin-runner.exe",
        ("native", "CallLocalFunction", False, None, None, "plugin-runner.exe", None),
    ),
    (
        "#1 native CallLocalFunction () from samp-server.exe",
        ("native", "CallLocalFunction", False, None, None, "samp-server.exe", None),
    ),
    (
        "#2 00000038 in main () at C:\\work\\tests\\bounds.pwn:21",
        ("amx", "main", False, "C:\\work\\tests\\bounds.pwn", 21, None, ""),
    ),
    (
        '#5 000001c4 in f4 (s[]=@00000018 "hi there") at /w/args.pwn:40',
        ("amx", "f4", False, "/w/args.pwn", 40, None, 's[]=@00000018 "hi there"'),
    ),
    (
        "#7 00000104 in f2 (bool:b1=true, bool:b2=false) at /w/args.pwn:12",
        ("amx", "f2", False, "/w/args.pwn", 12, None, "bool:b1=true, bool:b2=false"),
    ),
    (
        "#0 000001ac in foo (x=2) <Foo:on, undefined> at /w/states.pwn:31",
        ("amx", "foo", False, "/w/states.pwn", 31, None, "x=2"),
    ),
    (
        "#0 0000013c in function1 (... <76354974 variable arguments>) at /w/test.pwn:22",
        ("amx", "function1", False, "/w/test.pwn", 22, None, "... <76354974 variable arguments>"),
    ),
    (
        "#1 00000084 in public OnRuntimeError"
        " (code=1, &bool:suppress=@00000000 false) at /w/t.pwn:5",
        (
            "amx",
            "OnRuntimeError",
            True,
            "/w/t.pwn",
            5,
            None,
            "code=1, &bool:suppress=@00000000 false",
        ),
    ),
    (
        "#0 000000d8 in Float:GetDist (a=1) at /w/t.pwn:7",
        ("amx", "GetDist", False, "/w/t.pwn", 7, None, "a=1"),
    ),
    (
        "#0 00000094 in public OnFilterScriptInit () in gamemodes/rp.amx",
        ("amx", "OnFilterScriptInit", True, None, None, "gamemodes/rp.amx", ""),
    ),
    ("#3 00000010 in ?? () at /w/t.pwn:1", ("amx", "??", False, "/w/t.pwn", 1, None, "")),
    (
        "#0 00000010 in f () at C:\\Program Files\\samp server\\fs.pwn:12",
        ("amx", "f", False, "C:\\Program Files\\samp server\\fs.pwn", 12, None, ""),
    ),
    ("#0 00000010 in f () at <unknown file>:12", ("amx", "f", False, None, 12, None, "")),
    (
        '#0 00000010 in f (s[]=@00000018 "a) at b:1 c") at /w/t.pwn:9',
        ("amx", "f", False, "/w/t.pwn", 9, None, 's[]=@00000018 "a) at b:1 c"'),
    ),
]


@pytest.mark.parametrize(("text", "expected"), FRAME_CASES)
def test_parse_frame_handles_every_crashdetect_variant(text, expected):
    frame = parse_frame(text)
    assert frame is not None
    kind, function, public, file, line, module, args = expected
    assert (frame.kind, frame.function, frame.public) == (kind, function, public)
    assert (frame.file, frame.line, frame.module, frame.args) == (file, line, module, args)


@pytest.mark.parametrize(
    "text",
    [
        "#x foo",
        "hello",
        "#0 zzzz in f () at a:1",
        "#0 00000010 in f at a:1",
        "#0 00000010 in",
        "#0 ",
        "",
    ],
)
def test_parse_frame_rejects_non_frames(text):
    assert parse_frame(text) is None


def test_parse_frame_index_is_preserved():
    frame = parse_frame("#12 00000010 in f () at /w/t.pwn:9")
    assert frame is not None
    assert frame.index == 12


def test_parse_native_frame_extracts_callee_and_module():
    frame = parse_native_frame("#1 00401234 in ?? () in plugins/mysql.dll")
    assert frame is not None
    assert (frame.index, frame.callee, frame.module) == (1, "??", "plugins/mysql.dll")


def test_parse_native_frame_without_module():
    frame = parse_native_frame("#0 0046b2e7 in ?? ()")
    assert frame is not None
    assert frame.module is None


@pytest.mark.parametrize("text", ["#0 native X ()", "not a frame", "#0 zz in x ()"])
def test_parse_native_frame_rejects_other_lines(text):
    assert parse_native_frame(text) is None


def test_crashdetect_block_and_server_line_become_one_event():
    lines = [
        f'{STAMP} [debug] Run time error 4: "Array index out of bounds"',
        f"{STAMP} [debug]  Attempted to read/write array element"
        " at index 1000 in array of size 1000",
        f"{STAMP} [debug] AMX backtrace:",
        f"{STAMP} [debug] #0 000a1b2c in public OnPlayerUpdate (playerid=0)"
        " at gamemodes/rp.pwn:2210",
        f'{STAMP} Script[gamemodes/rp.amx]: Run time error 4: "Array index out of bounds"',
    ]
    events = events_of(lines)
    assert len(events) == 1
    event = events[0]
    assert (event.kind, event.code, event.script) == ("runtime_error", 4, "gamemodes/rp.amx")
    assert event.timestamp == "13:46:01"
    assert event.line_number == 1
    assert event.details == (
        "Attempted to read/write array element at index 1000 in array of size 1000",
    )
    frame = event.primary_frame
    assert frame is not None
    assert (frame.function, frame.line) == ("OnPlayerUpdate", 2210)


def test_server_line_with_different_wording_is_still_merged_by_error_code():
    lines = [
        f'{STAMP} [debug] Run time error 19: "File or function is not found"',
        f"{STAMP} [debug]  sscanf",
        f'{STAMP} Script[gamemodes/rp.amx]: Run time error 19: "File or function is not present"',
    ]
    events = events_of(lines)
    assert len(events) == 1
    assert events[0].message == "File or function is not found"
    assert events[0].script == "gamemodes/rp.amx"
    assert events[0].details == ("sscanf",)


def test_server_line_without_crashdetect_block_is_a_standalone_event():
    lines = [f'{STAMP} Script[gamemodes/rp.amx]: Run time error 4: "Array index out of bounds"'] * 3
    events = events_of(lines)
    assert len(events) == 3
    assert all(event.frames == () and event.script == "gamemodes/rp.amx" for event in events)
    assert [event.line_number for event in events] == [1, 2, 3]


def test_server_line_with_a_different_code_is_not_merged():
    lines = [
        f'{STAMP} [debug] Run time error 4: "Array index out of bounds"',
        f"{STAMP} [debug] AMX backtrace:",
        f"{STAMP} [debug] #0 000a1b2c in public A () at x.pwn:1",
        f'{STAMP} Script[gamemodes/rp.amx]: Run time error 11: "Divide by zero"',
    ]
    events = events_of(lines)
    assert [(event.code, event.script) for event in events] == [(4, None), (11, "gamemodes/rp.amx")]


def test_consecutive_crashdetect_blocks_yield_separate_events():
    lines = [
        f'{STAMP} [debug] Run time error 7: "Stack underflow"',
        f"{STAMP} [debug]  Stack pointer (STK) is 0x1c, stack top (STP) is 0x10",
        f"{STAMP} [debug] AMX backtrace:",
        f"{STAMP} [debug] #0 00000010 in public A () at x.pwn:1",
        f'{STAMP} [debug] Run time error 5: "Invalid memory access"',
        f"{STAMP} [debug] AMX backtrace:",
        f"{STAMP} [debug] #0 00000020 in public B () at x.pwn:2",
        f'{STAMP} Script[x.amx]: Run time error 5: "Invalid memory access"',
    ]
    events = events_of(lines)
    assert [(event.code, event.script) for event in events] == [(7, None), (5, "x.amx")]
    assert events[0].details == ("Stack pointer (STK) is 0x1c, stack top (STP) is 0x10",)


def test_crash_with_native_backtrace_ignores_register_dump():
    lines = [
        f"{STAMP} [debug] Server crashed while executing gamemodes/rp.amx",
        f"{STAMP} [debug] AMX backtrace:",
        f"{STAMP} [debug] #0 native SetPlayerName () in samp-server.exe",
        f"{STAMP} [debug] #1 000f2a10 in public OnPlayerConnect (playerid=3)"
        " at gamemodes/rp.pwn:120",
        f"{STAMP} [debug] Native backtrace:",
        f"{STAMP} [debug] #0 0046b2e7 in ?? () in samp-server.exe",
        f"{STAMP} [debug] #1 00401234 in ?? () in plugins/mysql.dll",
        f"{STAMP} [debug] Registers:",
        f"{STAMP} [debug] EAX: 00000000 EBX: 00000001",
        f"{STAMP} [debug] Loaded modules:",
        f"{STAMP} [debug] 00400000 - 00bb0000 samp-server.exe",
    ]
    events = events_of(lines)
    assert len(events) == 1
    event = events[0]
    assert (event.kind, event.script) == ("crash", "gamemodes/rp.amx")
    assert [frame.function for frame in event.frames] == ["SetPlayerName", "OnPlayerConnect"]
    assert [frame.module for frame in event.native_frames] == [
        "samp-server.exe",
        "plugins/mysql.dll",
    ]
    assert event.primary_frame is not None
    assert event.primary_frame.function == "OnPlayerConnect"


def test_crash_due_to_unknown_error_has_no_script():
    events = events_of([f"{STAMP} [debug] Server crashed due to an unknown error"])
    assert [(event.kind, event.script) for event in events] == [("crash", None)]


def test_long_callback_and_interrupt_are_recognised():
    lines = [
        f"{STAMP} [debug] Long callback execution detected (hang or performance issue)",
        f"{STAMP} [debug] AMX backtrace:",
        f"{STAMP} [debug] #0 00012345 in public OnGameModeInit () at gamemodes/rp.pwn:45",
        f"{STAMP} [debug] Server received interrupt signal while executing gamemodes/rp.amx",
        f"{STAMP} [debug] AMX backtrace:",
        f"{STAMP} [debug] #0 00012345 in public OnGameModeExit () at gamemodes/rp.pwn:90",
        f"{STAMP} [debug] Server received interrupt signal",
    ]
    events = events_of(lines)
    assert [event.kind for event in events] == ["long_call", "interrupt", "interrupt"]
    assert events[1].script == "gamemodes/rp.amx"
    assert events[2].script is None
    assert events[0].frames[0].function == "OnGameModeInit"


def test_missing_native_names_are_collected_as_details():
    lines = [
        f'{STAMP} [debug] Run time error 19: "File or function is not found"',
        f"{STAMP} [debug]  sscanf",
        f"{STAMP} [debug]  mysql_connect",
        f"{STAMP} Number of vehicle models: 0",
        f"{STAMP} [debug]  late_native",
    ]
    events = events_of(lines)
    assert len(events) == 1
    assert events[0].details == ("sscanf", "mysql_connect", "late_native")


def test_names_are_not_accepted_as_details_for_other_error_codes():
    lines = [
        f'{STAMP} [debug] Run time error 4: "Array index out of bounds"',
        f"{STAMP} [debug]  sscanf",
    ]
    assert events_of(lines)[0].details == ()


def test_detail_lines_need_exactly_one_leading_space():
    lines = [
        f'{STAMP} [debug] Run time error 19: "File or function is not found"',
        f"{STAMP} [debug]   indented_twice",
        f"{STAMP} [debug] no_leading_space",
    ]
    assert events_of(lines)[0].details == ()


def test_old_crashdetect_detail_wording_is_supported():
    lines = [
        '[debug] Run time error 4: "Array index out of bounds"',
        "[debug]  Accessing element at index 305419896 past array upper bound 0",
        "[debug] AMX backtrace:",
        "[debug] #0 native CallLocalFunction () from samp-server.exe",
        "[debug] #1 00000094 in public OnFilterScriptInit () at C:\\samp\\filterscripts\\fs.pwn:12",
    ]
    events = events_of(lines)
    assert events[0].timestamp is None
    assert events[0].details == ("Accessing element at index 305419896 past array upper bound 0",)
    assert events[0].primary_frame is not None
    assert events[0].primary_frame.file == "C:\\samp\\filterscripts\\fs.pwn"


def test_openmp_style_prefixes_are_supported():
    lines = [
        '[2026-10-01T14:29:46+0000] [Info] [debug] Run time error 11: "Divide by zero"',
        "[2026-10-01T14:29:46+0000] [Info] [debug] AMX backtrace:",
        "[2026-10-01T14:29:46+0000] [Info] [debug] #0 00000010 in public A () at x.pwn:3",
    ]
    events = events_of(lines)
    assert len(events) == 1
    assert events[0].timestamp == "2026-10-01T14:29:46+0000"


def test_standalone_crashdetect_log_without_debug_tag_is_supported():
    lines = [
        '[13:46:01] Run time error 4: "Array index out of bounds"',
        "[13:46:01]  Attempted to read/write array element at negative index -1",
        "[13:46:01] AMX backtrace:",
        "[13:46:01] #0 000a1b2c in public A () at x.pwn:9",
    ]
    events = events_of(lines)
    assert events[0].details == ("Attempted to read/write array element at negative index -1",)
    assert events[0].frames[0].line == 9


def test_chat_line_that_mentions_an_error_is_not_an_event():
    lines = [
        f'{STAMP} [chat] [0]Alice: Run time error 4: "Array index out of bounds"',
        f"{STAMP} [chat] [0]Alice: Server crashed while executing evil.amx",
        f"{STAMP} [chat] [0]Alice: Long callback execution detected",
    ]
    assert events_of(lines) == []


def test_single_unrelated_line_inside_a_block_does_not_break_it():
    lines = [
        f'{STAMP} [debug] Run time error 4: "Array index out of bounds"',
        f"{STAMP} [debug] AMX backtrace:",
        f"{STAMP} [join] Bob has joined the server (1:203.0.113.9)",
        f"{STAMP} [debug] #0 000a1b2c in public A () at x.pwn:9",
    ]
    assert len(events_of(lines)[0].frames) == 1


def test_block_is_closed_after_too_many_unrelated_lines():
    lines = [
        f'{STAMP} [debug] Run time error 4: "Array index out of bounds"',
        f"{STAMP} [debug] AMX backtrace:",
        f"{STAMP} [join] one",
        f"{STAMP} [join] two",
        f"{STAMP} [join] three",
        f"{STAMP} [debug] #0 000a1b2c in public A () at x.pwn:9",
    ]
    events = events_of(lines)
    assert len(events) == 1
    assert events[0].frames == ()


def test_pending_block_is_returned_by_flush_only():
    parser = LogParser()
    assert parser.feed(f'{STAMP} [debug] Run time error 4: "Array index out of bounds"') == []
    assert parser.has_open_block
    flushed = parser.flush()
    assert len(flushed) == 1
    assert not parser.has_open_block
    assert parser.flush() == []


def test_frame_count_is_capped():
    lines = [
        f'{STAMP} [debug] Run time error 4: "Array index out of bounds"',
        f"{STAMP} [debug] AMX backtrace:",
        *[f"{STAMP} [debug] #{n} 00000010 in f{n} () at x.pwn:{n + 1}" for n in range(200)],
    ]
    assert len(events_of(lines)[0].frames) == MAX_FRAMES


def test_detail_count_is_capped_per_error_kind():
    detail = f"{STAMP} [debug]  Attempted to read/write array element at index 5 in array of size 2"
    bounds = [f'{STAMP} [debug] Run time error 4: "Array index out of bounds"', *[detail] * 20]
    assert len(events_of(bounds)[0].details) == MAX_DETAILS
    names = [
        f'{STAMP} [debug] Run time error 19: "File or function is not found"',
        *[f"{STAMP} [debug]  native_{n}" for n in range(200)],
    ]
    assert len(events_of(names)[0].details) == MAX_NAME_DETAILS


def test_unparseable_frame_lines_do_not_break_the_block():
    lines = [
        f'{STAMP} [debug] Run time error 4: "Array index out of bounds"',
        f"{STAMP} [debug] AMX backtrace:",
        f"{STAMP} [debug] #0 garbage that is not a frame",
        f"{STAMP} [debug] #1 000a1b2c in public A () at x.pwn:9",
    ]
    event = events_of(lines)[0]
    assert [frame.function for frame in event.frames] == ["A"]


def test_unrelated_logs_produce_no_events_and_still_count_lines():
    parser = LogParser()
    for line in ["[13:00:00] [join] a", "random", "", "[chat] [1]B: hi"]:
        assert parser.feed(line) == []
    assert parser.line_number == 4
    assert not parser.has_open_block


def test_very_long_frame_line_is_parsed_quickly_and_safely():
    args = "x=1, " * 1500
    lines = [
        f'{STAMP} [debug] Run time error 4: "Array index out of bounds"',
        f"{STAMP} [debug] AMX backtrace:",
        f"{STAMP} [debug] #0 00000010 in public Big ({args}) at x.pwn:1",
    ]
    event = events_of(lines)[0]
    assert event.frames[0].function == "Big"
    assert event.frames[0].line == 1


NATIVE_FRAME_CASES = [
    ("#1 native CallLocalFunction () in samp03svr", "CallLocalFunction", "samp03svr"),
    ("#1 native CallLocalFunction () from samp03svr", "CallLocalFunction", "samp03svr"),
    ("#1 native CallLocalFunction () [080dfb90] from samp03svr", "CallLocalFunction", "samp03svr"),
    ("#1 native CallLocalFunction () [080DFB90] in samp03svr", "CallLocalFunction", "samp03svr"),
    ("#1 native strcmp () [00474110]", "strcmp", None),
    ("#1 native strcmp ()", "strcmp", None),
    (
        "#1 native Foo () [741d9830] from C:\\Program Files\\samp server\\samp-server.exe",
        "Foo",
        "C:\\Program Files\\samp server\\samp-server.exe",
    ),
]


@pytest.mark.parametrize(("text", "callee", "module"), NATIVE_FRAME_CASES)
def test_parse_frame_accepts_every_known_native_call_layout(text, callee, module):
    frame = parse_frame(text)
    assert frame is not None
    assert (frame.kind, frame.function, frame.public, frame.module) == (
        "native",
        callee,
        False,
        module,
    )
    assert (frame.file, frame.line, frame.args) == (None, None, None)


@pytest.mark.parametrize(
    "text",
    [
        "#1 native Foo () [zz] from x",
        "#1 native Foo () [] from x",
        "#1 native Foo () [080dfb90 from x",
        "#1 native Foo (x) in y",
        "#1 native () in y",
        "#1 native Foo () through y",
        "#1 native Foo () [0123456789abcdef0] from x",
    ],
)
def test_parse_frame_rejects_malformed_native_calls(text):
    assert parse_frame(text) is None


MODULE_MARKER_CASES = [
    ("#0 00060f1c in ?? (0x00000000) from XSR.amx", "??", False, "XSR.amx"),
    ("#0 00060f1c in ?? (0x00000000) in XSR.amx", "??", False, "XSR.amx"),
    (
        "#1 00060ff4 in public OnPlayerConnectEx (0x00000000) from XSR.amx",
        "OnPlayerConnectEx",
        True,
        "XSR.amx",
    ),
    (
        "#2 00006270 in public OnPlayerCommandText (0, 43242804) in Suhartawan World.amx",
        "OnPlayerCommandText",
        True,
        "Suhartawan World.amx",
    ),
    ("#2 00006270 in f () from   spaced.amx", "f", False, "spaced.amx"),
    ("#2 00006270 in f () from", "f", False, None),
    ("#2 00006270 in f ()", "f", False, None),
]


@pytest.mark.parametrize(("text", "function", "public", "module"), MODULE_MARKER_CASES)
def test_parse_frame_reads_the_module_after_either_marker(text, function, public, module):
    frame = parse_frame(text)
    assert frame is not None
    assert (frame.function, frame.public, frame.module) == (function, public, module)
    assert (frame.file, frame.line) == (None, None)


def test_parse_frame_uses_the_last_module_marker_when_both_appear():
    frame = parse_frame("#0 00060f1c in f (a) in b.amx) from c.amx")
    assert frame is not None
    assert frame.module == "c.amx"
    assert frame.args == "a) in b.amx"


def test_parse_frame_does_not_read_a_module_marker_inside_a_string_argument():
    frame = parse_frame('#0 00000010 in f (s[]=@00000018 "a) from b") at /w/t.pwn:9')
    assert frame is not None
    assert (frame.file, frame.line, frame.module) == ("/w/t.pwn", 9, None)
    assert frame.args == 's[]=@00000018 "a) from b"'


@pytest.mark.parametrize(
    ("text", "module"),
    [
        ("#1 00019d34 in ??", None),
        ("#1 00019d34 in ?? from base.amx", "base.amx"),
        ("#1 00019d34 in ?? in base.amx", "base.amx"),
    ],
)
def test_parse_frame_accepts_unnamed_frames_without_an_argument_list(text, module):
    frame = parse_frame(text)
    assert frame is not None
    assert (frame.kind, frame.function, frame.public, frame.module) == ("amx", "??", False, module)
    assert (frame.file, frame.line, frame.args) == (None, None, None)


@pytest.mark.parametrize(
    "text",
    [
        "#1 00019d34 in ??extra",
        "#1 00019d34 in ?",
        "#1 00019d34 in public ??",
        "#1 00019d34 in ?? through base.amx",
        "#1 in ??",
    ],
)
def test_parse_frame_rejects_unnamed_frame_lookalikes(text):
    assert parse_frame(text) is None


def test_module_names_are_truncated_to_a_fixed_length():
    long_name = "m" * 400
    for text in (
        f"#1 native Foo () in {long_name}",
        f"#1 00019d34 in ?? from {long_name}",
        f"#1 00019d34 in f () in {long_name}",
    ):
        frame = parse_frame(text)
        assert frame is not None
        assert frame.module == "m" * 260
    native = parse_native_frame(f"#1 00019d34 in f () in {long_name}")
    assert native is not None
    assert native.module == "m" * 260


@pytest.mark.parametrize(
    ("text", "callee", "module"),
    [
        (
            "#0 f7484e8b in _ZN10StackTraceC1EPv () in plugins/crashdetect.so",
            "_ZN10StackTraceC1EPv",
            "plugins/crashdetect.so",
        ),
        (
            "#0 f7484e8b in _ZN10StackTraceC1EPv () from plugins/crashdetect.so",
            "_ZN10StackTraceC1EPv",
            "plugins/crashdetect.so",
        ),
        ("#0 f7484e8b in f () from C:\\samp server\\x.exe", "f", "C:\\samp server\\x.exe"),
        ("#2 f779f410 in ??", "??", None),
        ("#0 f7484e8b in f ()", "f", None),
        ("#0 f7484e8b in f () via x", "f", None),
        ("#0 f7484e8b in f () from ", "f", None),
    ],
)
def test_parse_native_frame_reads_the_module_after_either_marker(text, callee, module):
    native = parse_native_frame(text)
    assert native is not None
    assert (native.callee, native.module) == (callee, module)


CRASH_TEXT = "Server crashed while executing {}"
INTERRUPT_TEXT = "Server received interrupt signal while executing {}"


@pytest.mark.parametrize(
    "script", ["example.amx", "EXAMPLE.AMX", "Example.Amx", "gamemodes/rp.amx"]
)
@pytest.mark.parametrize(
    ("template", "kind"), [(CRASH_TEXT, "crash"), (INTERRUPT_TEXT, "interrupt")]
)
def test_crash_and_interrupt_headers_accept_amx_file_names(template, kind, script):
    events = events_of([f"{STAMP} [debug] {template.format(script)}"])
    assert [(event.kind, event.script) for event in events] == [(kind, script)]


@pytest.mark.parametrize(
    "script",
    [
        "C:\\Program Files\\samp server\\my game.amx",
        "my game (2).amx",
        "<unknown>",
        "x" * 256 + ".amx",
    ],
)
@pytest.mark.parametrize(
    ("template", "kind"), [(CRASH_TEXT, "crash"), (INTERRUPT_TEXT, "interrupt")]
)
def test_crash_and_interrupt_headers_accept_unusual_but_plausible_names(template, kind, script):
    events = events_of([f"{STAMP} [debug] {template.format(script)}"])
    assert [(event.kind, event.script) for event in events] == [(kind, script)]


@pytest.mark.parametrize(
    "script",
    [
        "notes.txt",
        "gm.amx.bak",
        ".amx",
        "amx",
        "is a phrase players might type",
        "the tests",
        "x.amx extra",
        "<unknown> extra",
        "<UNKNOWN>",
        "x" * 257 + ".amx",
        "",
    ],
)
@pytest.mark.parametrize("template", [CRASH_TEXT, INTERRUPT_TEXT])
def test_crash_and_interrupt_headers_reject_text_that_is_not_an_amx_name(template, script):
    assert events_of([f"{STAMP} [debug] {template.format(script)}"]) == []


def test_crash_and_interrupt_headers_tolerate_trailing_whitespace():
    lines = [
        f"{STAMP} [debug] Server crashed while executing gm.amx  ",
        f"{STAMP} [debug] Server received interrupt signal while executing gm.amx\t",
    ]
    assert [(event.kind, event.script) for event in events_of(lines)] == [
        ("crash", "gm.amx"),
        ("interrupt", "gm.amx"),
    ]


LONG_CALL_TEXT = "Long callback execution detected (hang or performance issue)"


@pytest.mark.parametrize("suffix", ["", " ", "  \t"])
def test_long_callback_header_tolerates_trailing_whitespace(suffix):
    events = events_of([f"{STAMP} [debug] {LONG_CALL_TEXT}{suffix}"])
    assert [event.kind for event in events] == ["long_call"]


@pytest.mark.parametrize(
    "text",
    [
        "Long callback execution detected",
        "Long callback execution detected is not at line start",
        f"{LONG_CALL_TEXT} is a phrase players might type",
        "Long callback execution detected (hang or performance issues)",
        "Long callback execution detected (hang)",
        f"x {LONG_CALL_TEXT}",
        LONG_CALL_TEXT.lower(),
    ],
)
def test_long_callback_header_must_match_the_whole_line(text):
    assert events_of([f"{STAMP} [debug] {text}"]) == []


@pytest.mark.parametrize(
    "text",
    [
        'Run time error 4: "Array index out of bounds" and more',
        'Run time error 4: "x" "y"',
        'Run time error 4: "x"y',
        'Script[a.amx]: Run time error 4: "x" trailing',
    ],
)
def test_runtime_error_header_must_end_with_its_message(text):
    assert events_of([f"{STAMP} [debug] {text}"]) == []


def test_runtime_error_header_tolerates_trailing_whitespace():
    events = events_of([f'{STAMP} [debug] Run time error 4: "x"  \t'])
    assert [(event.code, event.message) for event in events] == [(4, "x")]


def header19(stamp: str = STAMP) -> str:
    return f'{stamp} [debug] Run time error 19: "File or function is not found"'


SCRIPT19 = f'{STAMP} Script[gamemodes/rp.amx]: Run time error 19: "File or function is not found"'


def test_repeated_empty_code_19_headers_report_one_event_with_the_script():
    events = events_of([header19(), header19(), SCRIPT19])
    assert [(e.kind, e.code, e.script, e.line_number) for e in events] == [
        ("runtime_error", 19, "gamemodes/rp.amx", 2)
    ]


def test_many_repeated_empty_code_19_headers_still_report_one_event():
    events = events_of([header19()] * 5 + [SCRIPT19])
    assert [(e.script, e.line_number) for e in events] == [("gamemodes/rp.amx", 5)]


def test_repeated_empty_code_19_headers_without_a_script_line_report_one_event():
    events = events_of([header19(), header19(), header19()])
    assert [(e.script, e.line_number) for e in events] == [(None, 3)]


def test_repeated_empty_header_tolerates_a_quiet_line_in_between():
    events = events_of([header19(), f"{STAMP} unrelated", header19(), SCRIPT19])
    assert [(e.script, e.line_number) for e in events] == [("gamemodes/rp.amx", 3)]


def test_code_19_headers_stay_separate_when_the_first_has_native_names():
    lines = [header19(), f"{STAMP} [debug]  Foo", header19(), SCRIPT19]
    events = events_of(lines)
    assert [(e.script, e.details, e.line_number) for e in events] == [
        (None, ("Foo",), 1),
        ("gamemodes/rp.amx", (), 3),
    ]


def test_code_19_headers_stay_separate_when_a_script_line_comes_between():
    events = events_of([header19(), SCRIPT19, header19(), SCRIPT19])
    assert [(e.script, e.line_number) for e in events] == [
        ("gamemodes/rp.amx", 1),
        ("gamemodes/rp.amx", 3),
    ]


def test_code_19_headers_stay_separate_when_the_first_is_followed_by_a_backtrace():
    lines = [header19(), f"{STAMP} [debug] AMX backtrace:", header19()]
    assert [e.line_number for e in events_of(lines)] == [1, 3]


def test_code_19_headers_with_different_messages_stay_separate():
    other = f'{STAMP} [debug] Run time error 19: "Another message"'
    assert [e.line_number for e in events_of([header19(), other])] == [1, 2]


@pytest.mark.parametrize("code", [4, 5, 9, 20, 22])
def test_repeated_empty_headers_of_other_codes_are_not_collapsed(code):
    header = f'{STAMP} [debug] Run time error {code}: "same"'
    assert [e.line_number for e in events_of([header, header])] == [1, 2]


def test_repeated_empty_header_does_not_swallow_a_different_kind_of_block():
    lines = [
        header19(),
        f"{STAMP} [debug] Long callback execution detected (hang or performance issue)",
    ]
    assert [(e.kind, e.line_number) for e in events_of(lines)] == [
        ("runtime_error", 1),
        ("long_call", 2),
    ]


def test_system_backtrace_label_starts_the_native_section():
    lines = [
        f"{STAMP} [debug] Server crashed while executing gm.amx",
        f"{STAMP} [debug] AMX backtrace:",
        f"{STAMP} [debug] #0 000a1b2c in public A () at x.pwn:9",
        f"{STAMP} [debug] System backtrace:",
        f"{STAMP} [debug] #0 70fa59a2 in AMXDebugInfo::Load () from C:\\samp\\crashdetect.DLL",
    ]
    event = events_of(lines)[0]
    assert [frame.function for frame in event.frames] == ["A"]
    assert [(n.callee, n.module) for n in event.native_frames] == [
        ("AMXDebugInfo::Load", "C:\\samp\\crashdetect.DLL")
    ]


def test_parse_frame_uses_the_last_occurrence_of_the_same_module_marker():
    frame = parse_frame("#0 00060f1c in f (a) in b.amx) in c.amx")
    assert frame is not None
    assert frame.module == "c.amx"
    assert frame.args == "a) in b.amx"


def test_code_19_headers_are_not_collapsed_with_a_header_of_another_code():
    same_text = f'{STAMP} [debug] Run time error 4: "File or function is not found"'
    assert [e.line_number for e in events_of([header19(), same_text])] == [1, 2]
