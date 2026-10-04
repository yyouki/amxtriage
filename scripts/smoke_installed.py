import argparse
import gzip
import json
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_LOG = ROOT / "examples" / "sample_server_log.txt"
SAMPLE_SOURCES = ROOT / "examples" / "gamemodes"
LEAK_MARKER = "hunter2-secret"
NEW_PROBLEM = (
    '[14:10:01] [debug] Run time error 11: "Division by zero"\n'
    "[14:10:01] [debug] AMX backtrace:\n"
    "[14:10:01] [debug] #0 000b00a4 in public OnVehicleDeath (vehicleid=7) at gamemodes/rp.pwn:90\n"
    '[14:10:01] Script[gamemodes/rp.amx]: Run time error 11: "Division by zero"\n'
)


class Smoke:
    def __init__(self, python: Path, workdir: Path) -> None:
        self.python = str(python)
        self.workdir = workdir
        self.failures = 0

    def run(self, *args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.python, "-m", "amxtriage", *args],
            input=stdin.decode("utf-8") if stdin is not None else None,
            capture_output=True,
            text=True,
            cwd=self.workdir,
            timeout=120,
            check=False,
        )

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        if not condition:
            self.failures += 1
        verdict = "PASS" if condition else "FAIL"
        extra = f"  {detail}" if detail and not condition else ""
        print(f"{verdict}  {name}{extra}")

    def watch(self, log: Path) -> tuple[int, str, str]:
        child = subprocess.Popen(
            [
                self.python,
                "-u",
                "-m",
                "amxtriage",
                "watch",
                str(log),
                "--from-start",
                "--poll-interval",
                "0.2",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.workdir,
        )
        if child.stdout is None or child.stderr is None:
            raise RuntimeError("the pipes of the watch process were not created")
        stdout = child.stdout
        seen: list[str] = []

        def pump() -> None:
            for line in stdout:
                seen.append(line)

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not any(
            "NEW  RUNTIME ERROR" in line for line in seen
        ):
            time.sleep(0.05)
        child.send_signal(signal.SIGINT)
        code = child.wait(timeout=30)
        reader.join(timeout=5)
        return code, "".join(seen), child.stderr.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test an installed amxtriage. "
        "Give the Python of the environment it is installed in."
    )
    parser.add_argument("python", type=Path, help="python executable of the clean environment")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="amxtriage-smoke-") as scratch:
        smoke = Smoke(args.python, Path(scratch))
        located = subprocess.run(
            [str(args.python), "-c", "import amxtriage, sys; print(amxtriage.__file__)"],
            capture_output=True,
            text=True,
            cwd=scratch,
            check=False,
        )
        smoke.check(
            "package is imported from the environment, not from the source tree",
            located.returncode == 0 and str(ROOT / "src") not in located.stdout,
            located.stdout.strip() or located.stderr.strip(),
        )

        version = smoke.run("--version")
        smoke.check(
            "--version", version.returncode == 0 and version.stdout.startswith("amxtriage ")
        )

        explain = smoke.run("explain", "4")
        smoke.check(
            "explain 4", explain.returncode == 0 and "Array index out of bounds" in explain.stdout
        )

        text = smoke.run("analyze", str(SAMPLE_LOG))
        smoke.check("analyze (text)", text.returncode == 0 and "5 distinct problems" in text.stdout)

        as_json = smoke.run("analyze", str(SAMPLE_LOG), "--format", "json")
        try:
            document = json.loads(as_json.stdout)
            valid = document["summary"]["matching_problems"] == 5
        except (ValueError, KeyError):
            valid = False
        smoke.check("analyze (json) is valid and has 5 problems", as_json.returncode == 0 and valid)

        markdown = smoke.run("analyze", str(SAMPLE_LOG), "--format", "markdown")
        smoke.check(
            "analyze (markdown)",
            markdown.returncode == 0 and markdown.stdout.startswith("# amxtriage report"),
        )

        packed = Path(scratch) / "sample.log.gz"
        packed.write_bytes(gzip.compress(SAMPLE_LOG.read_bytes()))
        zipped = smoke.run("analyze", str(packed))
        smoke.check(
            "analyze (.gz)", zipped.returncode == 0 and "5 distinct problems" in zipped.stdout
        )

        piped = smoke.run("analyze", "-", stdin=SAMPLE_LOG.read_bytes())
        smoke.check(
            "analyze (stdin)", piped.returncode == 0 and "5 distinct problems" in piped.stdout
        )

        smoke.check(
            "arguments hidden by default",
            LEAK_MARKER not in text.stdout and LEAK_MARKER not in as_json.stdout,
        )
        shown = smoke.run("analyze", str(SAMPLE_LOG), "--show-args")
        smoke.check("arguments shown with --show-args", LEAK_MARKER in shown.stdout)

        context = smoke.run("analyze", str(SAMPLE_LOG), "--source-dir", str(SAMPLE_SOURCES))
        smoke.check("source context", "SetPlayerName(playerid, name);" in context.stdout)

        baseline = Path(scratch) / "baseline.json"
        saved = smoke.run("analyze", str(SAMPLE_LOG), "--save-baseline", str(baseline))
        unchanged = smoke.run(
            "analyze", str(SAMPLE_LOG), "--baseline", str(baseline), "--fail-on-new"
        )
        later = Path(scratch) / "later.log"
        later.write_text(SAMPLE_LOG.read_text(encoding="utf-8") + NEW_PROBLEM, encoding="utf-8")
        changed = smoke.run("analyze", str(later), "--baseline", str(baseline), "--fail-on-new")
        smoke.check(
            "baseline workflow exits 0, 0, 1",
            (saved.returncode, unchanged.returncode, changed.returncode) == (0, 0, 1),
            f"{saved.returncode}, {unchanged.returncode}, {changed.returncode}",
        )

        missing = smoke.run("analyze", str(Path(scratch) / "missing.log"))
        smoke.check(
            "missing file gives exit 2 and no traceback",
            missing.returncode == 2
            and "Traceback" not in missing.stderr
            and "error:" in missing.stderr,
        )

        code, out, err = smoke.watch(SAMPLE_LOG)
        smoke.check(
            "watch announces problems and exits 0 on Ctrl+C",
            code == 0
            and "NEW  RUNTIME ERROR" in out
            and "watch summary" in out
            and "Traceback" not in err,
            f"exit {code}",
        )

    print(f"{smoke.failures} failure(s)")
    return 1 if smoke.failures else 0


if __name__ == "__main__":
    sys.exit(main())
