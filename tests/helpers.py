from amxtriage.parser import parse_lines


def events_of(lines):
    return list(parse_lines(lines))


def error_block(
    code: int = 4,
    function: str = "OnPlayerUpdate",
    file: str = "gamemodes/rp.pwn",
    line: int = 30,
    *,
    message: str = "Array index out of bounds",
    script_line: bool = True,
    stamp: str = "13:46:01",
) -> list[str]:
    lines = [
        f'[{stamp}] [debug] Run time error {code}: "{message}"',
        f"[{stamp}] [debug] AMX backtrace:",
        f"[{stamp}] [debug] #0 000a1b2c in public {function} (playerid=0) at {file}:{line}",
    ]
    if script_line:
        lines.append(f'[{stamp}] Script[gamemodes/rp.amx]: Run time error {code}: "{message}"')
    return lines
