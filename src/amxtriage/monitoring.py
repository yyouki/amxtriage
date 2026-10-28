"""Opt-in Linux host and amxtriage-process metrics for watch mode.

Host measurements are observations, not a zero-overhead guarantee. They describe the host and
amxtriage process, not the game-server process. Alert timings cover local export processing, not
the in-game chat delivery time.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from amxtriage.alerts import _open_append
from amxtriage.errors import InputError, OutputError
from amxtriage.textutil import sanitize

DEFAULT_METRICS_INTERVAL_SECONDS = 5.0
MAX_METRICS_RECORD_BYTES = 8192


def metrics_supported() -> bool:
    """Return whether the Linux procfs/sysfs backend is available for this host."""
    return sys.platform.startswith("linux")


class MetricsSampler:
    """Read Linux /proc and /sys counters with injectable paths and clock for tests."""

    def __init__(
        self,
        interval_seconds: float = DEFAULT_METRICS_INTERVAL_SECONDS,
        *,
        proc_root: Path = Path("/proc"),
        sys_root: Path = Path("/sys"),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 1.0 <= interval_seconds <= 3600.0:
            raise InputError("metrics interval must be between 1 and 3600 seconds")
        self.interval_seconds = interval_seconds
        self.proc_root = proc_root
        self.sys_root = sys_root
        self._clock = clock
        self._last_at: float | None = None
        self._cpu: tuple[int, int] | None = None
        self._process_ticks: int | None = None
        self._disk: tuple[int, int] | None = None
        self._alert_count = 0
        self._alert_total_ms = 0.0
        self._alert_max_ms: float | None = None
        self._alert_latest_ms: float | None = None

    def due(self) -> bool:
        now = self._clock()
        return self._last_at is None or now - self._last_at >= self.interval_seconds

    @property
    def has_sampled(self) -> bool:
        return self._last_at is not None

    @property
    def has_pending_alerts(self) -> bool:
        return self._alert_count > 0

    def record_alert_processing(self, elapsed_ms: float) -> None:
        """Record local alert export time; game-chat delivery latency is measured separately."""
        if elapsed_ms < 0:
            return
        self._alert_count += 1
        self._alert_total_ms += elapsed_ms
        self._alert_max_ms = (
            elapsed_ms if self._alert_max_ms is None else max(self._alert_max_ms, elapsed_ms)
        )
        self._alert_latest_ms = elapsed_ms

    def _cpu_counters(self) -> tuple[int, int] | None:
        try:
            fields = (self.proc_root / "stat").read_text(encoding="ascii").splitlines()[0].split()
            values = [int(value) for value in fields[1:]]
            if fields[0] != "cpu" or len(values) < 4:
                return None
            return sum(values), values[3] + (values[4] if len(values) > 4 else 0)
        except (OSError, ValueError, IndexError):
            return None

    def _process_counters(self) -> tuple[int, int] | None:
        try:
            raw = (self.proc_root / "self" / "stat").read_text(encoding="ascii")
            fields = raw[raw.rfind(")") + 2 :].split()
            ticks = int(fields[11]) + int(fields[12])
            rss = int(fields[21]) * int(os.sysconf("SC_PAGE_SIZE"))
            return (ticks, rss) if rss >= 0 else None
        except (OSError, ValueError, IndexError, AttributeError):
            return None

    def _memory_counters(self) -> tuple[int, int] | None:
        try:
            values: dict[str, int] = {}
            for line in (self.proc_root / "meminfo").read_text(encoding="ascii").splitlines():
                key, separator, tail = line.partition(":")
                parts = tail.split()
                if separator and parts and key in {"MemTotal", "MemAvailable"}:
                    values[key] = int(parts[0]) * 1024
            total, available = values["MemTotal"], values["MemAvailable"]
            return (total, available) if total > 0 and 0 <= available <= total else None
        except (OSError, ValueError, KeyError):
            return None

    def _disk_counters(self) -> tuple[int, int] | None:
        """Read whole-device counters; stacked block-device layers can double-count I/O."""
        try:
            names = {item.name for item in (self.sys_root / "block").iterdir() if item.is_dir()}
            totals = [0, 0]
            found = False
            for line in (self.proc_root / "diskstats").read_text(encoding="ascii").splitlines():
                fields = line.split()
                if len(fields) >= 10 and fields[2] in names:
                    totals[0] += int(fields[5]) * 512
                    totals[1] += int(fields[9]) * 512
                    found = True
            return (totals[0], totals[1]) if found else None
        except (OSError, ValueError):
            return None

    def sample(self) -> dict[str, object]:
        now = self._clock()
        elapsed = None if self._last_at is None else now - self._last_at
        cpu = self._cpu_counters()
        process = self._process_counters()
        memory = self._memory_counters()
        disk = self._disk_counters()

        cpu_pct: float | None = None
        if cpu and self._cpu and elapsed and elapsed > 0:
            total_delta, idle_delta = cpu[0] - self._cpu[0], cpu[1] - self._cpu[1]
            if total_delta > 0 and 0 <= idle_delta <= total_delta:
                cpu_pct = round((total_delta - idle_delta) * 100 / total_delta, 2)

        process_pct: float | None = None
        if process and self._process_ticks is not None and elapsed and elapsed > 0:
            tick_delta = process[0] - self._process_ticks
            ticks_per_second = int(os.sysconf("SC_CLK_TCK"))
            if tick_delta >= 0 and ticks_per_second > 0:
                # One-core percentage can exceed 100 when the process uses multiple cores.
                process_pct = round(tick_delta * 100 / ticks_per_second / elapsed, 2)

        read_rate: float | None = None
        write_rate: float | None = None
        if disk and self._disk and elapsed and elapsed > 0:
            reads, writes = disk[0] - self._disk[0], disk[1] - self._disk[1]
            if reads >= 0 and writes >= 0:
                read_rate, write_rate = round(reads / elapsed, 2), round(writes / elapsed, 2)

        self._last_at = now
        if cpu:
            self._cpu = cpu
        if process:
            self._process_ticks = process[0]
        if disk:
            self._disk = disk

        unavailable: list[str] = []
        if cpu is None:
            unavailable.append("system.cpu_percent")
        if process is None:
            unavailable.extend(["process.cpu_percent_one_core", "process.rss_bytes"])
        if memory is None:
            unavailable.append("system.memory")
        if disk is None:
            unavailable.append("disk_io")
        used_pct = round((memory[0] - memory[1]) * 100 / memory[0], 2) if memory else None
        count = self._alert_count
        alert_metrics = {
            "count": count,
            "average_ms": round(self._alert_total_ms / count, 3) if count else None,
            "max_ms": round(self._alert_max_ms, 3) if self._alert_max_ms is not None else None,
            "latest_ms": (
                round(self._alert_latest_ms, 3) if self._alert_latest_ms is not None else None
            ),
        }
        self._alert_count, self._alert_total_ms = 0, 0.0
        self._alert_max_ms = self._alert_latest_ms = None

        return {
            "schema_version": 1,
            "tool": "amxtriage",
            "event_type": "metrics.sample",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "interval_seconds": round(elapsed, 3) if elapsed is not None else None,
            "status": "partial" if unavailable else "ok",
            "unavailable": unavailable,
            "system": {
                "cpu_percent": cpu_pct,
                "memory_total_bytes": memory[0] if memory else None,
                "memory_available_bytes": memory[1] if memory else None,
                "memory_used_percent": used_pct,
            },
            "process": {
                "pid": os.getpid(),
                "cpu_percent_one_core": process_pct,
                "rss_bytes": process[1] if process else None,
            },
            "disk_io": {
                "read_bytes_total": disk[0] if disk else None,
                "write_bytes_total": disk[1] if disk else None,
                "read_bytes_per_second": read_rate,
                "write_bytes_per_second": write_rate,
                "scope": "visible whole block devices; stacked layers may double-count",
            },
            "alert_processing": alert_metrics,
        }


class JsonlMetricsSink:
    """Append bounded local metrics; a write error disables only this optional sink."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.disabled = False
        self.failure_reason: str | None = None
        self.warning_emitted = False

    def emit(self, sample: dict[str, object]) -> bool:
        if self.disabled:
            return False
        try:
            record = json.dumps(
                sample, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ) + "\n"
            data = record.encode("utf-8")
            if len(data) > MAX_METRICS_RECORD_BYTES:
                raise OutputError("metrics record exceeds the configured size limit")
            descriptor = _open_append(self.path)
            try:
                offset = 0
                while offset < len(data):
                    written = os.write(descriptor, data[offset:])
                    if written <= 0:
                        raise OutputError("metrics output write made no progress")
                    offset += written
            finally:
                os.close(descriptor)
        except (OSError, OutputError, ValueError, TypeError) as error:
            self.disabled = True
            self.failure_reason = sanitize(str(error) or type(error).__name__, 300)
            return False
        return True
