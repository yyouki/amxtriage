import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from amxtriage.analysis import analyze_logs
from amxtriage.baseline import save_baseline
from helpers import error_block

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="signal based shutdown is only tested on POSIX"
)

SRC = Path(__file__).resolve().parent.parent / "src"
WAIT_SECONDS = 30.0


class WatchProcess:
    def __init__(self, log, *extra):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SRC)
        env["PYTHONIOENCODING"] = "utf-8"
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "amxtriage",
                "watch",
                str(log),
                "--poll-interval",
                "0.1",
                *extra,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        self.out: list[str] = []
        self.err: list[str] = []
        self._threads = [
            threading.Thread(target=self._pump, args=(self.process.stdout, self.out), daemon=True),
            threading.Thread(target=self._pump, args=(self.process.stderr, self.err), daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    @staticmethod
    def _pump(stream, sink):
        for raw in iter(stream.readline, b""):
            sink.append(raw.decode("utf-8", errors="replace"))

    def text(self, stream="out"):
        return "".join(self.out if stream == "out" else self.err)

    def wait_for(self, needle, stream="out"):
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            if needle in self.text(stream):
                return True
            if self.process.poll() is not None:
                break
            time.sleep(0.05)
        return needle in self.text(stream)

    def stop(self, sig):
        self.process.send_signal(sig)
        code = self.process.wait(timeout=WAIT_SECONDS)
        for thread in self._threads:
            thread.join(timeout=5)
        return code

    def kill(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=10)


@pytest.fixture
def watcher_factory():
    started = []

    def start(log, *extra):
        watcher = WatchProcess(log, *extra)
        started.append(watcher)
        assert watcher.wait_for("watching", "err"), watcher.text("err")
        return watcher

    yield start
    for watcher in started:
        watcher.kill()


def append(path, lines):
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def test_each_new_problem_is_announced_once_and_summarised_on_sigint(tmp_path, watcher_factory):
    log = tmp_path / "server_log.txt"
    log.write_text("[13:45:00] server started\n")
    watcher = watcher_factory(log)

    append(log, error_block(4, "OnPlayerUpdate"))
    append(log, error_block(11, "OnDialogResponse", message="Divide by zero"))
    assert watcher.wait_for("RUNTIME ERROR 11")
    assert watcher.wait_for("RUNTIME ERROR 4")

    append(log, error_block(4, "OnPlayerUpdate", stamp="13:50:00"))
    append(log, error_block(4, "OnPlayerUpdate", stamp="13:51:00"))
    time.sleep(0.8)
    assert watcher.text().count("NEW  RUNTIME ERROR 4") == 1

    assert watcher.stop(signal.SIGINT) == 0
    output = watcher.text()
    assert "watch summary" in output
    assert "RUNTIME ERROR 4: Array index out of bounds   x3" in output
    assert "RUNTIME ERROR 11: Divide by zero   x1" in output


def test_sigterm_also_shuts_down_cleanly_with_a_summary(tmp_path, watcher_factory):
    log = tmp_path / "server_log.txt"
    log.write_text("")
    watcher = watcher_factory(log)
    append(log, error_block(4, "OnPlayerUpdate"))
    assert watcher.wait_for("RUNTIME ERROR 4")
    assert watcher.stop(signal.SIGTERM) == 0
    assert "watch summary" in watcher.text()
    assert "Traceback" not in watcher.text("err")


def test_a_block_at_the_end_of_the_log_is_flushed_when_the_log_goes_quiet(
    tmp_path, watcher_factory
):
    log = tmp_path / "server_log.txt"
    log.write_text("")
    watcher = watcher_factory(log)
    append(
        log,
        [
            "[13:55:00] [debug] Long callback execution detected (hang or performance issue)",
            "[13:55:00] [debug] AMX backtrace:",
            "[13:55:00] [debug] #0 00012345 in public OnGameModeInit () at gamemodes/rp.pwn:15",
        ],
    )
    assert watcher.wait_for("LONG CALLBACK")
    assert watcher.stop(signal.SIGINT) == 0


def test_existing_content_is_ignored_unless_from_start_is_given(tmp_path, watcher_factory):
    log = tmp_path / "server_log.txt"
    log.write_text("\n".join(error_block(4, "OldProblem")) + "\n")
    watcher = watcher_factory(log)
    append(log, error_block(11, "NewProblem", message="Divide by zero"))
    assert watcher.wait_for("RUNTIME ERROR 11")
    assert "OldProblem" not in watcher.text()
    assert watcher.stop(signal.SIGINT) == 0


def test_from_start_announces_problems_already_in_the_log(tmp_path, watcher_factory):
    log = tmp_path / "server_log.txt"
    log.write_text("\n".join(error_block(4, "OldProblem")) + "\n")
    watcher = watcher_factory(log, "--from-start")
    assert watcher.wait_for("RUNTIME ERROR 4")
    assert watcher.stop(signal.SIGINT) == 0


def test_baseline_suppresses_known_problems_in_watch_mode(tmp_path, watcher_factory):
    known_log = tmp_path / "known.log"
    known_log.write_text("\n".join(error_block(4, "OnPlayerUpdate")) + "\n")
    baseline = tmp_path / "baseline.json"
    save_baseline(str(baseline), analyze_logs([str(known_log)]).aggregator.sorted_groups())

    log = tmp_path / "server_log.txt"
    log.write_text("")
    watcher = watcher_factory(log, "--baseline", str(baseline))
    append(log, error_block(4, "OnPlayerUpdate"))
    append(log, error_block(11, "BrandNew", message="Divide by zero"))
    assert watcher.wait_for("RUNTIME ERROR 11")
    assert watcher.text().count("NEW  RUNTIME ERROR 4") == 0
    assert watcher.stop(signal.SIGINT) == 0


def test_log_rotation_during_watch_is_followed(tmp_path, watcher_factory):
    log = tmp_path / "server_log.txt"
    log.write_text("")
    watcher = watcher_factory(log)
    append(log, error_block(4, "BeforeRotation"))
    assert watcher.wait_for("RUNTIME ERROR 4")

    log.rename(tmp_path / "server_log.txt.1")
    log.write_text("\n".join(error_block(11, "AfterRotation", message="Divide by zero")) + "\n")
    assert watcher.wait_for("RUNTIME ERROR 11")
    assert watcher.stop(signal.SIGINT) == 0


def test_watching_a_missing_file_fails_fast_with_a_clean_error(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    result = subprocess.run(
        [sys.executable, "-m", "amxtriage", "watch", str(tmp_path / "missing.log")],
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert result.returncode == 2
    assert result.stderr.count(b"error: cannot open") == 1
    assert b"Traceback" not in result.stderr
