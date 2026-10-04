import argparse
import random
from collections.abc import Sequence
from pathlib import Path

NORMAL_TEMPLATES = (
    "[{stamp}] [join] Player{n} has joined the server ({slot}:203.0.113.{octet})",
    "[{stamp}] [part] Player{n} has left the server ({slot}:1)",
    "[{stamp}] [chat] [{slot}]Player{n}: message number {n}",
    "[{stamp}] Incoming connection: 203.0.113.{octet}:{port} id: {slot}",
    "[{stamp}] [cmd] [{slot}]Player{n}: /stats",
)

PROBLEMS = (
    (4, "Array index out of bounds", "OnPlayerUpdate", 2210),
    (4, "Array index out of bounds", "OnPlayerUpdate", 2230),
    (11, "Divide by zero", "OnDialogResponse", 880),
    (4, "Array index out of bounds", "OnVehicleDamageStatusUpdate", 4410),
    (5, "Invalid memory access", "OnPlayerCommandText", 1520),
    (10, "Native function failed", "OnPlayerSpawn", 305),
    (3, "Stack/heap collision (insufficient stack size)", "OnPlayerDeath", 760),
    (4, "Array index out of bounds", "SavePlayerData", 3100),
    (11, "Divide by zero", "UpdateEconomy", 3920),
    (4, "Array index out of bounds", "OnPlayerEnterCheckpoint", 1010),
)


def stamp_for(counter: int) -> str:
    seconds = counter // 5
    return f"{(seconds // 3600) % 24:02d}:{(seconds // 60) % 60:02d}:{seconds % 60:02d}"


def problem_block(rng: random.Random, stamp: str, weights: Sequence[float]) -> list[str]:
    code, message, function, line = rng.choices(PROBLEMS, weights=weights)[0]
    lines = [
        f'[{stamp}] [debug] Run time error {code}: "{message}"',
        f"[{stamp}] [debug] AMX backtrace:",
        f"[{stamp}] [debug] #0 000a1b2c in public {function} (playerid={rng.randrange(500)})"
        f" at gamemodes/rp.pwn:{line}",
        f'[{stamp}] Script[gamemodes/rp.amx]: Run time error {code}: "{message}"',
    ]
    if code == 4:
        lines.insert(1, f"[{stamp}] [debug]  Attempted to read/write array element at index 1000 in array of size 1000")
    return lines


def crash_block(rng: random.Random, stamp: str) -> list[str]:
    module = rng.choice(("samp-server.exe", "plugins/mysql.dll", "plugins/streamer.dll"))
    return [
        f"[{stamp}] [debug] Server crashed while executing gamemodes/rp.amx",
        f"[{stamp}] [debug] AMX backtrace:",
        f"[{stamp}] [debug] #0 native SetPlayerName () in samp-server.exe",
        f"[{stamp}] [debug] #1 000f2a10 in public OnPlayerConnect (playerid=3) at gamemodes/rp.pwn:120",
        f"[{stamp}] [debug] Native backtrace:",
        f"[{stamp}] [debug] #0 0046b2e7 in ?? () in {module}",
        f"[{stamp}] [debug] Registers:",
    ]


def generate(total_lines: int, error_ratio: float, seed: int) -> list[str]:
    rng = random.Random(seed)
    weights = [1.0 / (rank + 1) for rank in range(len(PROBLEMS))]
    lines: list[str] = []
    while len(lines) < total_lines:
        stamp = stamp_for(len(lines))
        draw = rng.random()
        if draw < error_ratio * 0.01:
            lines.extend(crash_block(rng, stamp))
        elif draw < error_ratio:
            lines.extend(problem_block(rng, stamp, weights))
        else:
            template = rng.choice(NORMAL_TEMPLATES)
            lines.append(
                template.format(
                    stamp=stamp,
                    n=rng.randrange(100000),
                    slot=rng.randrange(500),
                    octet=rng.randrange(1, 255),
                    port=rng.randrange(1024, 65535),
                )
            )
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a synthetic SA-MP server log.")
    parser.add_argument("output", type=Path)
    parser.add_argument("--lines", type=int, default=1_000_000)
    parser.add_argument("--error-ratio", type=float, default=0.02)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    lines = generate(args.lines, args.error_ratio, args.seed)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"wrote {len(lines):,} lines to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
