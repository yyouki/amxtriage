from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from amxtriage.monitoring import JsonlMetricsSink, MetricsSampler


def write_snapshot(
    proc: Path,
    sysroot: Path,
    *,
    cpu: str,
    ticks: tuple[int, int],
    rss_pages: int,
    read_sectors: int = 100,
    write_sectors: int = 200,
) -> None:
    proc.mkdir(parents=True, exist_ok=True)
    (proc / "self").mkdir(exist_ok=True)
    (proc / "stat").write_text(f"cpu {cpu}\n", encoding="ascii")
    fields = ["R"] + ["0"] * 21
    fields[11], fields[12], fields[21] = str(ticks[0]), str(ticks[1]), str(rss_pages)
    (proc / "self" / "stat").write_text(
        "42 (amxtriage worker) " + " ".join(fields), encoding="ascii"
    )
    (proc / "meminfo").write_text(
        "MemTotal: 1024000 kB\nMemAvailable: 512000 kB\n", encoding="ascii"
    )
    (proc / "diskstats").write_text(
        f"8 0 sda 10 0 {read_sectors} 0 20 0 {write_sectors} 0 0 0\n",
        encoding="ascii",
    )
    (sysroot / "block" / "sda").mkdir(parents=True, exist_ok=True)


def nested(sample: dict[str, object], key: str) -> dict[str, object]:
    value = sample[key]
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def test_sampler_reports_cpu_memory_process_rss_and_disk_rates(tmp_path: Path) -> None:
    proc, sysroot = tmp_path / "proc", tmp_path / "sys"
    write_snapshot(proc, sysroot, cpu="100 0 50 800 50 0 0 0 0 0", ticks=(100, 50), rss_pages=20)
    clock = [100.0]
    sampler = MetricsSampler(5, proc_root=proc, sys_root=sysroot, clock=lambda: clock[0])
    first = sampler.sample()
    assert first["status"] == "ok"
    assert nested(first, "system")["memory_used_percent"] == 50.0
    assert nested(first, "process")["rss_bytes"] == 20 * 4096

    write_snapshot(
        proc,
        sysroot,
        cpu="150 0 70 920 60 0 0 0 40 10",
        ticks=(125, 75),
        rss_pages=30,
        read_sectors=150,
        write_sectors=240,
    )
    clock[0] += 5.0
    second = sampler.sample()
    assert nested(second, "system")["cpu_percent"] == 35.0
    assert nested(second, "process")["cpu_percent_one_core"] == 10.0
    assert nested(second, "disk_io")["read_bytes_per_second"] == 5120.0
    assert nested(second, "disk_io")["write_bytes_per_second"] == 4096.0


def test_alert_processing_timing_is_aggregated_per_sample(tmp_path: Path) -> None:
    proc, sysroot = tmp_path / "proc", tmp_path / "sys"
    write_snapshot(proc, sysroot, cpu="100 0 50 800 50 0 0 0 0 0", ticks=(100, 50), rss_pages=20)
    sampler = MetricsSampler(1, proc_root=proc, sys_root=sysroot, clock=lambda: 10.0)
    sampler.sample()
    sampler.record_alert_processing(4.2)
    sampler.record_alert_processing(5.8)
    assert nested(sampler.sample(), "alert_processing") == {
        "count": 2,
        "average_ms": 5.0,
        "max_ms": 5.8,
        "latest_ms": 5.8,
    }


def test_metrics_sink_writes_jsonl_and_refuses_symlink(tmp_path: Path) -> None:
    target = tmp_path / "metrics.jsonl"
    sink = JsonlMetricsSink(str(target))
    assert sink.emit({"schema_version": 1, "event_type": "metrics.sample"})
    assert sink.emit({"schema_version": 1, "event_type": "metrics.sample"})
    records = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2

    protected = tmp_path / "protected.jsonl"
    protected.write_text("preserve\n", encoding="utf-8")
    link = tmp_path / "link.jsonl"
    try:
        link.symlink_to(protected)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable on this runner")
    unsafe = JsonlMetricsSink(str(link))
    assert not unsafe.emit({"schema_version": 1})
    assert unsafe.disabled
    assert protected.read_text(encoding="utf-8") == "preserve\n"
