"""Measure local watch-mode resource use and alert latency on a synthetic log.

Linux-only: reads process counters from /proc. Results describe this host and workload, not a live
SA-MP/open.mp server and not player ping. No network connections or server commands are used.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProcessSample:
    cpu_user_seconds: float
    cpu_system_seconds: float
    resident_bytes: int
    read_bytes: int
    write_bytes: int


def process_sample(pid: int) -> ProcessSample | None:
    """Read Linux process CPU, RSS and I/O counters from procfs."""
    proc_root = Path("/proc") / str(pid)
    try:
        stat_text = (proc_root / "stat").read_text(encoding="ascii")
        closing_paren = stat_text.rfind(")")
        fields = stat_text[closing_paren + 2 :].split()
        io_values = {
            key: int(value)
            for key, value in (
                line.split(":", maxsplit=1)
                for line in (proc_root / "io").read_text(encoding="ascii").splitlines()
            )
        }
        clock_ticks = os.sysconf("SC_CLK_TCK")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return ProcessSample(
            cpu_user_seconds=int(fields[11]) / clock_ticks,
            cpu_system_seconds=int(fields[12]) / clock_ticks,
            resident_bytes=int(fields[21]) * page_size,
            read_bytes=io_values["read_bytes"],
            write_bytes=io_values["write_bytes"],
        )
    except (FileNotFoundError, IndexError, KeyError, OSError, ValueError):
        return None


def diagnostic_block(index: int) -> str:
    """Return one distinct, representative crashdetect-style runtime error block."""
    stamp = "13:46:01"
    line = 100 + index
    function = f"OnBenchmark{index}"
    return "\n".join(
        (
            f'[{stamp}] [debug] Run time error 4: "Array index out of bounds"',
            f"[{stamp}] [debug] AMX backtrace:",
            f"[{stamp}] [debug] #0 000a1b2c in public {function} (playerid=0) "
            f"at gamemodes/benchmark.pwn:{line}",
            f"[{stamp}] Script[gamemodes/benchmark.amx]: Run time error 4: "
            '"Array index out of bounds"',
            "",
        )
    )


def percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def run_benchmark(event_count: int, timeout_seconds: float) -> dict[str, object]:
    if sys.platform != "linux":
        raise RuntimeError("this benchmark currently requires Linux /proc counters")

    with tempfile.TemporaryDirectory(prefix="amxtriage-watch-benchmark-") as raw_temp:
        root = Path(raw_temp)
        log_path = root / "server_log.txt"
        alert_path = root / "alerts.jsonl"
        log_path.write_text("[13:45:00] synthetic benchmark started\n", encoding="utf-8")

        command = [
            sys.executable,
            "-m",
            "amxtriage",
            "watch",
            str(log_path),
            "--poll-interval",
            "0.1",
            "--alert-jsonl",
            str(alert_path),
            "--alert-cooldown",
            "0",
            "--alert-max-per-minute",
            "300",
        ]
        process = subprocess.Popen(
            command,
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        latencies: list[float] = []
        samples: list[ProcessSample] = []
        started = time.monotonic()

        try:
            time.sleep(0.2)
            if process.poll() is not None:
                raise RuntimeError(f"watch process exited early with code {process.returncode}")
            first_sample = process_sample(process.pid)
            if first_sample is None:
                raise RuntimeError("could not read initial process metrics from /proc")
            samples.append(first_sample)
            deadline = time.monotonic() + timeout_seconds

            for index in range(event_count):
                if time.monotonic() >= deadline:
                    raise RuntimeError("benchmark exceeded its overall timeout")
                event_started = time.monotonic()
                with log_path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(diagnostic_block(index))
                    handle.flush()

                event_deadline = min(deadline, time.monotonic() + 5.0)
                expected_records = index + 1
                while time.monotonic() < event_deadline:
                    sample = process_sample(process.pid)
                    if sample is not None:
                        samples.append(sample)
                    if process.poll() is not None:
                        raise RuntimeError(
                            f"watch process exited during event {index} with code "
                            f"{process.returncode}"
                        )
                    if alert_path.exists():
                        rows = alert_path.read_text(encoding="utf-8").splitlines()
                        if len(rows) >= expected_records:
                            latencies.append(time.monotonic() - event_started)
                            break
                    time.sleep(0.01)
                else:
                    raise RuntimeError(
                        f"no structured alert arrived for synthetic event {index} within 5 seconds"
                    )

            final_sample = process_sample(process.pid)
            if final_sample is not None:
                samples.append(final_sample)
            process.send_signal(signal.SIGINT)
            exit_code = process.wait(timeout=5.0)
            if exit_code != 0:
                raise RuntimeError(f"watch process exited with code {exit_code}")
            rows = alert_path.read_text(encoding="utf-8").splitlines()
            if len(rows) != event_count:
                raise RuntimeError(
                    f"expected {event_count} alerts but received {len(rows)}"
                )

            start_sample = samples[0]
            end_sample = samples[-1]
            max_rss = max(sample.resident_bytes for sample in samples)
            elapsed = time.monotonic() - started
            return {
                "schema_version": 1,
                "tool": "amxtriage",
                "mode": "synthetic-watch-benchmark",
                "host_scope": "local Linux process; not a live game-server or ping benchmark",
                "events_requested": event_count,
                "alerts_received": len(rows),
                "elapsed_seconds": round(elapsed, 6),
                "alert_latency_ms": {
                    "min": round(min(latencies) * 1000, 3),
                    "median": round(sorted(latencies)[len(latencies) // 2] * 1000, 3),
                    "p95": round(percentile_95(latencies) * 1000, 3),
                    "max": round(max(latencies) * 1000, 3),
                },
                "process_metrics": {
                    "cpu_user_seconds_delta": round(
                        end_sample.cpu_user_seconds - start_sample.cpu_user_seconds, 6
                    ),
                    "cpu_system_seconds_delta": round(
                        end_sample.cpu_system_seconds - start_sample.cpu_system_seconds, 6
                    ),
                    "max_sampled_resident_bytes": max_rss,
                    "kernel_read_bytes_delta": max(
                        0, end_sample.read_bytes - start_sample.read_bytes
                    ),
                    "kernel_write_bytes_delta": max(
                        0, end_sample.write_bytes - start_sample.write_bytes
                    ),
                },
                "notes": [
                    "Synthetic workload only; values depend on host, filesystem, Python, "
                    "and poll interval.",
                    "Kernel-accounted I/O is not a guarantee of physical disk writes.",
                    "Do not infer live server CPU, RAM, disk I/O or player ping from this result.",
                ],
            }
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5.0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure local amxtriage watch alert latency and process resources."
    )
    parser.add_argument("--events", type=int, default=10, help="distinct synthetic alerts (1-250)")
    parser.add_argument("--timeout", type=float, default=60.0, help="overall timeout in seconds")
    args = parser.parse_args(argv)
    if not 1 <= args.events <= 250:
        parser.error("--events must be between 1 and 250")
    if not 1.0 <= args.timeout <= 600.0:
        parser.error("--timeout must be between 1 and 600 seconds")
    try:
        result = run_benchmark(args.events, args.timeout)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"benchmark failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
