import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOGUE = Path(__file__).resolve().parent / "mutants.json"
EQUIVALENT = frozenset({"V12"})
RUN_TIMEOUT_SECONDS = 120
SKIPPED = shutil.ignore_patterns(
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".coverage",
    ".venv",
    "build",
    "dist",
    "*.egg-info",
)
FAILURE_LINE = re.compile(r"^(?:FAILED|ERROR) tests/(\w+)\.py", re.MULTILINE)


@dataclass(frozen=True)
class Edit:
    old: str
    new: str
    count: int


@dataclass(frozen=True)
class Mutant:
    ident: str
    file: str
    description: str
    edits: tuple[Edit, ...]


@dataclass(frozen=True)
class Outcome:
    ident: str
    killed: bool
    killed_by: tuple[str, ...]
    seconds: float


def load_catalogue() -> list[Mutant]:
    raw = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    return [
        Mutant(
            item["id"],
            item["file"],
            item["description"],
            tuple(Edit(edit["old"], edit["new"], edit["count"]) for edit in item["edits"]),
        )
        for item in raw
    ]


def invalid_specifications(mutants: list[Mutant]) -> list[str]:
    problems: list[str] = []
    for mutant in mutants:
        text = (ROOT / mutant.file).read_text(encoding="utf-8")
        for edit in mutant.edits:
            found = text.count(edit.old)
            if found != edit.count:
                problems.append(
                    f"{mutant.ident}: expected {edit.count} occurrence(s) of {edit.old!r}, "
                    f"found {found}"
                )
    return problems


def run_pytest(work: Path, extra: list[str]) -> tuple[bool, tuple[str, ...]]:
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": str(work),
    }
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
        "-q",
        "--tb=no",
        "-rfE",
        *extra,
    ]
    child = subprocess.Popen(
        command,
        cwd=work,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=environment,
        start_new_session=True,
    )
    try:
        output, _ = child.communicate(timeout=RUN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.communicate()
        return False, ("TIMEOUT",)
    failed = tuple(sorted(set(FAILURE_LINE.findall(output))))
    if child.returncode != 0 and not failed:
        return False, ("UNKNOWN",)
    return child.returncode == 0, failed


def evaluate(mutant: Mutant) -> Outcome:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="amxtriage-mutant-") as scratch:
        work = Path(scratch) / "tree"
        shutil.copytree(ROOT, work, ignore=SKIPPED)
        target = work / mutant.file
        text = target.read_text(encoding="utf-8")
        for edit in mutant.edits:
            text = text.replace(edit.old, edit.new)
        target.write_text(text, encoding="utf-8")
        passed, failed = run_pytest(work, ["--ignore=tests/test_watch.py"])
        if passed:
            passed, failed = run_pytest(work, ["tests/test_watch.py"])
    return Outcome(mutant.ident, not passed, failed, time.monotonic() - started)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Break the code on purpose and check that the tests notice. POSIX only."
    )
    parser.add_argument("ids", nargs="*", help="run only these mutant ids")
    parser.add_argument("--check", action="store_true", help="only validate the catalogue")
    parser.add_argument("--list", action="store_true", dest="list_only", help="list the mutants")
    args = parser.parse_args(argv)

    mutants = load_catalogue()
    problems = invalid_specifications(mutants)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 2
    if args.check:
        print(f"{len(mutants)} mutants, every specification matches the source")
        return 0
    if args.list_only:
        for mutant in mutants:
            print(f"{mutant.ident:5} {Path(mutant.file).name:14} {mutant.description}")
        return 0
    unknown = sorted(set(args.ids) - {mutant.ident for mutant in mutants})
    if unknown:
        print(f"unknown mutant id(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    control = evaluate(Mutant("CONTROL", "pyproject.toml", "unmodified tree", ()))
    if control.killed:
        print(f"the unmodified tree fails its own tests: {', '.join(control.killed_by)}")
        return 2
    selected = [mutant for mutant in mutants if not args.ids or mutant.ident in args.ids]
    survivors: list[str] = []
    for mutant in selected:
        outcome = evaluate(mutant)
        status = "killed" if outcome.killed else "SURVIVED"
        print(f"{outcome.ident:5} {status:8} {', '.join(outcome.killed_by)}", flush=True)
        if not outcome.killed and outcome.ident not in EQUIVALENT:
            survivors.append(f"{outcome.ident} ({mutant.description})")
    print(f"{len(selected)} mutants run, {len(survivors)} unexpected survivor(s)")
    for line in survivors:
        print(f"  survived: {line}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
