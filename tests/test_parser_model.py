import random
from typing import Any

import pytest

from amxtriage.parser import parse_lines
from helpers import project_event

STAMPS = [
    "12:00:01",
    "23/06/2017 23:19:57",
    "28/03/2019 - 04:00:40",
    "2023-09-03 12:41:38",
    "2026-09-28T15:55:49+0330",
    None,
]
NOISE = [
    "[join] Alice has joined the server (0:127.0.0.1)",
    "[chat] [Bob]: hello there",
    "[connection] incoming connection: 127.0.0.1:2256 id: 1",
    "Number of vehicle models: 0",
    "Error: Function not registered: 'ExampleNative'",
    "plain text without structure",
    "",
    "[EXAMPLE_DEBUG]: value=1",
    "Loading filterscript 'example.amx'...",
]
MESSAGES = {
    1: "Forced exit",
    2: "Assertion failed",
    3: "Stack/heap collision (insufficient stack size)",
    4: "Array index out of bounds",
    5: "Invalid memory access",
    6: "Invalid instruction",
    7: "Stack underflow",
    8: "Heap underflow",
    11: "Divide by zero",
    27: "General error (unknown or unspecific error)",
}
NATIVE_NAMES = ["mysql_connect", "cache_get_row_count", "sscanf", "_name2", "@native"]
FUNCTIONS = ["OnPlayerConnect", "OnGameModeInit", "cmd_test", "_helper", "S@@_OnTick", "Calc2"]
TAGGED = [("Float:CalcDistance", "CalcDistance"), ("bool:IsValid", "IsValid")]
PATHS = [
    "gamemodes/example.pwn",
    "gamemodes/include/hooks.inc",
    "C:\\Games\\server\\gm.pwn",
    "C:\\Program Files\\samp server\\gm.pwn",
    "filterscripts/a_b-c.pwn",
    "/home/user/server/gm.pwn",
]
MODULES = ["example.amx", "My Game.AMX", "samp03svr", "plugins/streamer.so", "samp-server.exe"]
LOCATION_ARGS = [
    "",
    "playerid=3",
    'playerid=0, cmdtext[]=@0297b810 "/test"',
    "... <4 arguments>",
    's[]=@00000018 "hi (there) in here"',
    "&Float:f=@00003fb0 1.50000, bool:b=true",
    'text[]=@00001000 "look at this"',
]
PLAIN_ARGS = ["0x00000000", "0, 43242804", "", "..."]
NATIVE_SYMBOLS = [
    "_Z13GetStackTraceRSt6vectorI10StackFrameSaIS0_EEPv",
    "__libc_start_main",
    "AMXDebugInfo::Load",
]
SCRIPT_NAMES = ["example.amx", "My Game.AMX", "gamemodes/rp.amx", "<unknown>"]
OPEN_BLOCK_LIMIT = 2


class LogModel:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.style = rng.randrange(3)
        self.lines: list[str] = []
        self.events: list[dict[str, Any]] = []

    def emit(self, line: str) -> None:
        self.lines.append(line)

    def tagged(self, stamp: str | None, text: str) -> str:
        if self.style == 0:
            body = f"[debug] {text}"
        elif self.style == 1:
            body = text
        else:
            body = f"[Info] [debug] {text}"
        return f"[{stamp}] {body}" if stamp is not None else body

    def server_line(self, stamp: str | None, text: str) -> str:
        return f"[{stamp}] {text}" if stamp is not None else text

    def noise(self, count: int) -> None:
        for _ in range(count):
            text = self.rng.choice(NOISE)
            stamp = self.rng.choice(STAMPS)
            self.emit(self.server_line(stamp, text))

    def inner_noise(self) -> None:
        if self.rng.random() < 0.15:
            self.noise(self.rng.randint(1, OPEN_BLOCK_LIMIT))

    def pick_stamp(self, header_stamp: str | None) -> str | None:
        if self.rng.random() < 0.85:
            return header_stamp
        return self.rng.choice(STAMPS)

    def location(self) -> tuple[str, int]:
        return self.rng.choice(PATHS), self.rng.randint(1, 99999)

    def amx_frame(self, index: int) -> tuple[str, list[Any]]:
        rng = self.rng
        address = f"{rng.randrange(16**8):08x}"
        head = f"#{index} {address} in "
        form = rng.randrange(12)
        args = rng.choice(LOCATION_ARGS)
        plain = rng.choice(PLAIN_ARGS)
        name = rng.choice(FUNCTIONS)
        path, line = self.location()
        module = rng.choice(MODULES)
        marker = rng.choice(["in", "from"])
        if form == 0:
            text = f"{head}public {name} ({args}) at {path}:{line}"
            return text, [index, "amx", name, True, path, line, None]
        if form == 1:
            text = f"{head}{name} ({args}) at {path}:{line}"
            return text, [index, "amx", name, False, path, line, None]
        if form == 2:
            return f"{head}main ({args}) at {path}:{line}", [
                index,
                "amx",
                "main",
                False,
                path,
                line,
                None,
            ]
        if form == 3:
            raw, short = rng.choice(TAGGED)
            text = f"{head}{raw} ({args}) at {path}:{line}"
            return text, [index, "amx", short, False, path, line, None]
        if form == 4:
            text = f"{head}public {name} ({plain}) {marker} {module}"
            return text, [index, "amx", name, True, None, None, module]
        if form == 5:
            text = f"{head}?? ({plain}) {marker} {module}"
            return text, [index, "amx", "??", False, None, None, module]
        if form == 6:
            text = f"{head}?? ({args}) at {path}:{line}"
            return text, [index, "amx", "??", False, path, line, None]
        if form == 7:
            return f"{head}??", [index, "amx", "??", False, None, None, None]
        if form == 8:
            text = f"{head}{name} ({args}) <Fsm:run, idle> at {path}:{line}"
            return text, [index, "amx", name, False, path, line, None]
        if form == 9:
            text = f"{head}public {name} ({args}) at <unknown file>:{line}"
            return text, [index, "amx", name, True, None, line, None]
        if form == 10:
            return f"{head}public {name} ()", [index, "amx", name, True, None, None, None]
        return f"{head}public {name} () at :0", [index, "amx", name, True, None, None, None]

    def native_call_frame(self, index: int) -> tuple[str, list[Any]]:
        rng = self.rng
        name = rng.choice(NATIVE_NAMES)
        module = rng.choice(MODULES)
        address = f"{rng.randrange(16**8):08x}"
        form = rng.randrange(5)
        if form == 0:
            return f"#{index} native {name} () in {module}", [
                index,
                "native",
                name,
                False,
                None,
                None,
                module,
            ]
        if form == 1:
            return f"#{index} native {name} () from {module}", [
                index,
                "native",
                name,
                False,
                None,
                None,
                module,
            ]
        if form == 2:
            text = f"#{index} native {name} () [{address}] from {module}"
            return text, [index, "native", name, False, None, None, module]
        if form == 3:
            return f"#{index} native {name} ()", [index, "native", name, False, None, None, None]
        return f"#{index} native {name} () [{address}]", [
            index,
            "native",
            name,
            False,
            None,
            None,
            None,
        ]

    def native_backtrace_frame(self, index: int) -> tuple[str, list[Any]]:
        rng = self.rng
        address = f"{rng.randrange(16**8):08x}"
        symbol = rng.choice([*NATIVE_SYMBOLS, "??"])
        module = rng.choice(MODULES)
        marker = rng.choice(["in", "from"])
        if rng.random() < 0.25:
            return f"#{index} {address} in ??", [index, "??", None]
        return f"#{index} {address} in {symbol} () {marker} {module}", [index, symbol, module]

    def backtrace(self, stamp: str | None, frames_out: list[list[Any]], count: int) -> None:
        self.inner_noise()
        self.emit(self.tagged(self.pick_stamp(stamp), "AMX backtrace:"))
        for _ in range(count):
            self.inner_noise()
            index = self.rng.randrange(100)
            if self.rng.random() < 0.25:
                text, expected = self.native_call_frame(index)
            else:
                text, expected = self.amx_frame(index)
            self.emit(self.tagged(self.pick_stamp(stamp), text))
            frames_out.append(expected)

    def native_section(self, stamp: str | None, out: list[list[Any]], count: int) -> None:
        self.inner_noise()
        label = self.rng.choice(["Native backtrace:", "System backtrace:"])
        self.emit(self.tagged(self.pick_stamp(stamp), label))
        for _ in range(count):
            self.inner_noise()
            text, expected = self.native_backtrace_frame(self.rng.randrange(40))
            self.emit(self.tagged(self.pick_stamp(stamp), text))
            out.append(expected)

    def detail_lines(self, code: int) -> list[str]:
        rng = self.rng
        stk = f"0x{rng.randrange(4096):X}"
        other = f"0x{rng.randrange(4096):X}"
        if code == 4:
            roll = rng.random()
            if roll < 0.4:
                size = rng.randrange(1, 100)
                return [
                    "Attempted to read/write array element at index "
                    f"{rng.randrange(5000)} in array of size {size}"
                ]
            if roll < 0.7:
                negative = f"-{rng.randrange(1, 500)}"
                return [f"Attempted to read/write array element at negative index {negative}"]
            return [
                f"Accessing element at index {rng.randrange(5000)} "
                f"past array upper bound {rng.randrange(100)}"
            ]
        if code == 3:
            return [f"Stack pointer (STK) is {stk}, heap pointer (HEA) is {other}"]
        if code == 7:
            return [f"Stack pointer (STK) is {stk}, stack top (STP) is {other}"]
        if code == 8:
            return [f"Heap pointer (HEA) is {stk}, heap bottom (HLW) is {other}"]
        if code == 6:
            return [
                f"Unknown opcode 0x{rng.randrange(255):x} at address 0x{rng.randrange(65535):08X}"
            ]
        return []

    def event(self, kind: str, line_number: int, stamp: str | None, **fields: Any) -> None:
        self.events.append(
            {
                "kind": kind,
                "line_number": line_number,
                "timestamp": stamp,
                "code": fields.get("code"),
                "message": fields.get("message"),
                "script": fields.get("script"),
                "details": fields.get("details", []),
                "frames": fields.get("frames", []),
                "native_frames": fields.get("native_frames", []),
            }
        )

    def script_line(self, stamp: str | None, code: int, vary: bool = True) -> str:
        path = self.rng.choice(
            ["gamemodes/example.amx", "filterscripts/one.amx", "gamemodes/a b.amx"]
        )
        self.script_path = path
        message = MESSAGES.get(code, "File or function is not found")
        used = self.pick_stamp(stamp) if vary else stamp
        return self.server_line(used, f'Script[{path}]: Run time error {code}: "{message}"')

    def runtime_error(self) -> None:
        rng = self.rng
        code = rng.choice(list(MESSAGES))
        stamp = rng.choice(STAMPS)
        line_number = len(self.lines) + 1
        message = MESSAGES[code]
        self.emit(self.tagged(stamp, f'Run time error {code}: "{message}"'))
        details = self.detail_lines(code)
        for text in details:
            self.inner_noise()
            self.emit(self.tagged(self.pick_stamp(stamp), f" {text}"))
        frames: list[list[Any]] = []
        if rng.random() < 0.9:
            self.backtrace(stamp, frames, rng.randint(0, 5))
        script = None
        if rng.random() < 0.4:
            self.noise(rng.randint(0, OPEN_BLOCK_LIMIT))
            self.emit(self.script_line(stamp, code))
            script = self.script_path
        self.event(
            "runtime_error",
            line_number,
            stamp,
            code=code,
            message=message,
            script=script,
            details=details,
            frames=frames,
        )

    def not_found(self) -> None:
        rng = self.rng
        stamp = rng.choice(STAMPS)
        line_number = len(self.lines) + 1
        message = "File or function is not found"
        self.emit(self.tagged(stamp, f'Run time error 19: "{message}"'))
        names = rng.sample(NATIVE_NAMES, rng.randint(1, 3))
        for name in names:
            self.inner_noise()
            self.emit(self.tagged(self.pick_stamp(stamp), f" {name}"))
        script = None
        if rng.random() < 0.6:
            self.noise(rng.randint(0, OPEN_BLOCK_LIMIT))
            self.emit(self.script_line(stamp, 19))
            script = self.script_path
        self.event(
            "runtime_error",
            line_number,
            stamp,
            code=19,
            message=message,
            script=script,
            details=names,
        )

    def standalone_script(self) -> None:
        rng = self.rng
        self.noise(OPEN_BLOCK_LIMIT + 1)
        stamp = rng.choice(STAMPS)
        code = rng.choice([4, 19])
        line_number = len(self.lines) + 1
        self.emit(self.script_line(stamp, code, vary=False))
        message = MESSAGES.get(code, "File or function is not found")
        self.event(
            "runtime_error", line_number, stamp, code=code, message=message, script=self.script_path
        )

    def crash(self) -> None:
        rng = self.rng
        stamp = rng.choice(STAMPS)
        line_number = len(self.lines) + 1
        script = rng.choice(SCRIPT_NAMES) if rng.random() < 0.7 else None
        if script is None:
            self.emit(self.tagged(stamp, "Server crashed due to an unknown error"))
        else:
            self.emit(self.tagged(stamp, f"Server crashed while executing {script}"))
        frames: list[list[Any]] = []
        natives: list[list[Any]] = []
        if script is not None and rng.random() < 0.8:
            self.backtrace(stamp, frames, rng.randint(0, 4))
        if rng.random() < 0.9:
            self.native_section(stamp, natives, rng.randint(0, 5))
        for label in ("Registers:", "EAX: 00000000 EBX: 00004e1d", "ESI: f7347000 EDI: 00000000"):
            self.emit(self.tagged(stamp, label))
        self.event("crash", line_number, stamp, script=script, frames=frames, native_frames=natives)

    def interrupt(self) -> None:
        rng = self.rng
        stamp = rng.choice(STAMPS)
        line_number = len(self.lines) + 1
        script = rng.choice(SCRIPT_NAMES) if rng.random() < 0.7 else None
        text = "Server received interrupt signal"
        if script is not None:
            text += f" while executing {script}"
        self.emit(self.tagged(stamp, text))
        frames: list[list[Any]] = []
        natives: list[list[Any]] = []
        self.backtrace(stamp, frames, rng.randint(0, 4))
        if rng.random() < 0.5:
            self.native_section(stamp, natives, rng.randint(0, 4))
        self.event(
            "interrupt", line_number, stamp, script=script, frames=frames, native_frames=natives
        )

    def long_call(self) -> None:
        stamp = self.rng.choice(STAMPS)
        line_number = len(self.lines) + 1
        self.emit(
            self.tagged(stamp, "Long callback execution detected (hang or performance issue)")
        )
        frames: list[list[Any]] = []
        self.backtrace(stamp, frames, self.rng.randint(0, 5))
        self.event("long_call", line_number, stamp, frames=frames)

    def build(self) -> None:
        items = [
            self.runtime_error,
            self.runtime_error,
            self.not_found,
            self.standalone_script,
            self.crash,
            self.interrupt,
            self.long_call,
        ]
        for _ in range(self.rng.randint(1, 14)):
            self.rng.choice(items)()
            if self.rng.random() < 0.5:
                self.noise(self.rng.randint(0, 5))


@pytest.mark.parametrize("seed", range(400))
def test_random_logs_built_from_the_documented_grammar_parse_exactly_as_modelled(seed: int) -> None:
    model = LogModel(random.Random(seed))
    model.build()
    parsed = [project_event(event) for event in parse_lines(model.lines)]
    assert parsed == model.events


@pytest.mark.parametrize("seed", range(100))
def test_two_logs_joined_by_unrelated_lines_do_not_influence_each_other(seed: int) -> None:
    first = LogModel(random.Random(seed))
    second = LogModel(random.Random(10_000 + seed))
    first.build()
    second.build()
    separator = ["[join] unrelated"] * (OPEN_BLOCK_LIMIT + 1)
    offset = len(first.lines) + len(separator)
    joined = [*first.lines, *separator, *second.lines]
    parsed = [project_event(event) for event in parse_lines(joined)]
    shifted = [{**event, "line_number": event["line_number"] + offset} for event in second.events]
    assert parsed == [*first.events, *shifted]
