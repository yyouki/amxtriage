import gzip
import io
import time
import tracemalloc
from pathlib import Path

import pytest

from amxtriage import cli
from amxtriage.analysis import analyze_logs
from amxtriage.errors import InputError
from amxtriage.reader import CHUNK_SIZE, LineSplitter, iter_lines, open_log

LINE = b"x" * 99 + b"\n"


def text_of(size: int) -> bytes:
    full, rest = divmod(size, len(LINE))
    data = LINE * full
    if rest:
        data += b"y" * (rest - 1) + b"\n"
    assert len(data) == size
    return data


def lines_of(data: bytes, max_bytes: int | None) -> list[str]:
    stream = io.BytesIO(data)
    return list(iter_lines(stream, LineSplitter(), "input.log", max_bytes))


def gzip_of_repeated(chunk: bytes, times: int, level: int = 1) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=level) as handle:
        for _ in range(times):
            handle.write(chunk)
    return buffer.getvalue()


class CountingBytesIO(io.BytesIO):
    consumed = 0

    def read(self, size: int | None = -1) -> bytes:
        data = super().read(size)
        self.consumed += len(data)
        return data


class EndlessText:
    def __init__(self) -> None:
        self.returned = 0

    def read(self, size: int = -1) -> bytes:
        count = CHUNK_SIZE if size < 0 else size
        self.returned += count
        return (LINE * (count // len(LINE) + 1))[:count]


def test_an_input_of_exactly_the_limit_is_accepted() -> None:
    assert len(lines_of(text_of(1000), 1000)) == 10


def test_an_input_one_byte_over_the_limit_is_rejected() -> None:
    with pytest.raises(InputError, match="larger than the limit of 1000 bytes"):
        lines_of(text_of(1001), 1000)


def test_without_a_limit_any_size_is_accepted() -> None:
    assert len(lines_of(text_of(3 * CHUNK_SIZE + 17), None)) > 0


def test_a_limit_of_zero_bytes_accepts_only_empty_input() -> None:
    assert lines_of(b"", 0) == []
    with pytest.raises(InputError, match="larger than the limit"):
        lines_of(b"a\n", 0)


def test_the_error_names_the_option_and_the_way_to_remove_the_limit() -> None:
    with pytest.raises(InputError) as caught:
        lines_of(text_of(2000), 1000)
    message = str(caught.value)
    assert "input.log" in message
    assert "--max-input-bytes" in message
    assert "0 for no limit" in message
    assert "after decompression" in message


@pytest.mark.parametrize("limit", [1, 99, 100, CHUNK_SIZE - 1, CHUNK_SIZE, CHUNK_SIZE + 1])
def test_the_stream_is_never_read_beyond_the_limit_plus_one_byte(limit: int) -> None:
    endless = EndlessText()
    with pytest.raises(InputError):
        list(iter_lines(endless, LineSplitter(), "endless", limit))
    assert endless.returned <= limit + 1


def test_an_endless_source_without_a_limit_keeps_being_read() -> None:
    endless = EndlessText()
    stream = iter_lines(endless, LineSplitter(), "endless")
    for _ in range(100_000):
        next(stream)
    assert endless.returned > 0


def test_a_highly_compressed_input_is_stopped_early_and_cheaply() -> None:
    archive = gzip_of_repeated(text_of(CHUNK_SIZE), 64)
    assert len(archive) * 50 < 64 * CHUNK_SIZE
    source = CountingBytesIO(archive)
    stream = gzip.GzipFile(fileobj=source)
    tracemalloc.start()
    started = time.perf_counter()
    try:
        with pytest.raises(InputError, match="larger than the limit of 4194304 bytes"):
            list(iter_lines(stream, LineSplitter(), "bomb.gz", 4 * CHUNK_SIZE))
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert source.consumed < len(archive) // 4
    assert elapsed < 10
    assert peak < 48 * CHUNK_SIZE


def test_members_of_a_multi_member_archive_are_counted_together() -> None:
    member = gzip.compress(text_of(400_000))
    two = io.BytesIO(member * 2)
    three = io.BytesIO(member * 3)
    ok = list(iter_lines(gzip.GzipFile(fileobj=two), LineSplitter(), "two.gz", 1_000_000))
    assert len(ok) > 0
    with pytest.raises(InputError, match="larger than the limit"):
        list(iter_lines(gzip.GzipFile(fileobj=three), LineSplitter(), "three.gz", 1_000_000))


def test_a_gzip_inside_a_gzip_is_rejected_as_binary(tmp_path: Path) -> None:
    path = tmp_path / "nested.gz"
    path.write_bytes(gzip.compress(gzip.compress(b"line\n" * 100)))
    with pytest.raises(InputError, match="binary"):
        analyze_logs([str(path)])


def test_a_truncated_archive_is_reported_as_a_read_failure(tmp_path: Path) -> None:
    path = tmp_path / "cut.gz"
    path.write_bytes(gzip.compress(text_of(200_000))[:-40])
    with pytest.raises(InputError, match="failed while reading"):
        analyze_logs([str(path)])


def test_a_wrong_checksum_is_reported_as_a_read_failure(tmp_path: Path) -> None:
    data = bytearray(gzip.compress(text_of(5000)))
    data[-6] ^= 0xFF
    path = tmp_path / "crc.gz"
    path.write_bytes(bytes(data))
    with pytest.raises(InputError, match="failed while reading"):
        analyze_logs([str(path)])


def test_garbage_after_the_archive_is_reported_as_a_read_failure(tmp_path: Path) -> None:
    path = tmp_path / "tail.gz"
    path.write_bytes(gzip.compress(text_of(5000)) + b"not a gzip member")
    with pytest.raises(InputError, match="failed while reading"):
        analyze_logs([str(path)])


def test_a_single_endless_line_inside_an_archive_is_bounded_in_memory(tmp_path: Path) -> None:
    path = tmp_path / "oneline.gz"
    path.write_bytes(gzip_of_repeated(b"z" * CHUNK_SIZE, 32))
    tracemalloc.start()
    try:
        result = analyze_logs([str(path)], max_input_bytes=64 * CHUNK_SIZE)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result.truncated_lines == 1
    assert peak < 48 * CHUNK_SIZE


def test_analyze_logs_applies_the_limit_to_every_input_separately(tmp_path: Path) -> None:
    first = tmp_path / "a.log"
    second = tmp_path / "b.log"
    first.write_bytes(text_of(1000))
    second.write_bytes(text_of(1000))
    assert analyze_logs([str(first), str(second)], max_input_bytes=1000).lines_read == 20
    second.write_bytes(text_of(1001))
    with pytest.raises(InputError, match=r"b\.log"):
        analyze_logs([str(first), str(second)], max_input_bytes=1000)


def test_open_log_still_streams_plain_and_compressed_files_alike(tmp_path: Path) -> None:
    plain = tmp_path / "plain.log"
    packed = tmp_path / "packed.log"
    plain.write_bytes(text_of(5000))
    packed.write_bytes(gzip.compress(text_of(5000)))
    for path in (plain, packed):
        with open_log(str(path)) as stream:
            assert len(list(iter_lines(stream, LineSplitter(), str(path), 5000))) == 50
        with open_log(str(path)) as stream, pytest.raises(InputError):
            list(iter_lines(stream, LineSplitter(), str(path), 4999))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0", 0),
        ("1", 1),
        ("1048576", 1048576),
        ("1K", 1024),
        ("1k", 1024),
        ("2M", 2 * 1024**2),
        ("3m", 3 * 1024**2),
        ("4G", 4 * 1024**3),
        ("4g", 4 * 1024**3),
        (" 7M ", 7 * 1024**2),
        ("0K", 0),
    ],
)
def test_sizes_accept_a_number_with_an_optional_unit(text: str, expected: int) -> None:
    assert cli._size(text) == expected


@pytest.mark.parametrize(
    "text", ["", "-1", "1.5G", "12T", "1KB", "K", "abc", "1 K", "1_000", "+5", "9" * 16]
)
def test_sizes_reject_everything_else(text: str) -> None:
    import argparse

    with pytest.raises(argparse.ArgumentTypeError, match="invalid size"):
        cli._size(text)


@pytest.fixture
def log_file(tmp_path: Path) -> Path:
    path = tmp_path / "server_log.txt"
    path.write_bytes(text_of(2048))
    return path


def test_the_cli_rejects_an_oversized_input_and_produces_no_output_file(
    log_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "report.txt"
    code = cli.main(["analyze", str(log_file), "--max-input-bytes", "1K", "-o", str(report)])
    captured = capsys.readouterr()
    assert code == cli.EXIT_ERROR
    assert "larger than the limit of 1024 bytes" in captured.err
    assert captured.out == ""
    assert not report.exists()


def test_the_cli_accepts_an_input_of_exactly_the_limit(
    log_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(["analyze", str(log_file), "--max-input-bytes", "2K"])
    captured = capsys.readouterr()
    assert code == cli.EXIT_OK
    assert captured.err == ""
    assert captured.out.strip() != ""


def test_the_cli_has_no_limit_by_default_and_zero_removes_it(
    log_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["analyze", str(log_file)]) == cli.EXIT_OK
    assert cli.main(["analyze", str(log_file), "--max-input-bytes", "0"]) == cli.EXIT_OK
    assert capsys.readouterr().err == ""


def test_the_cli_stops_a_gzip_bomb_with_a_clear_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bomb = tmp_path / "bomb.log.gz"
    bomb.write_bytes(gzip_of_repeated(text_of(CHUNK_SIZE), 128))
    started = time.perf_counter()
    code = cli.main(["analyze", str(bomb), "--max-input-bytes", "2M"])
    assert time.perf_counter() - started < 10
    assert code == cli.EXIT_ERROR
    assert "after decompression" in capsys.readouterr().err


def test_the_cli_applies_the_limit_to_standard_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class FakeStdin:
        buffer = io.BytesIO(text_of(5000))

    monkeypatch.setattr("sys.stdin", FakeStdin())
    assert cli.main(["analyze", "-", "--max-input-bytes", "4999"]) == cli.EXIT_ERROR
    assert "larger than the limit of 4999 bytes" in capsys.readouterr().err


def test_the_cli_rejects_an_invalid_limit(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(["analyze", "x.log", "--max-input-bytes", "lots"])
    assert caught.value.code == 2
    assert "invalid size" in capsys.readouterr().err


def test_the_cli_has_no_default_limit_for_a_multi_megabyte_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    big = tmp_path / "big.log"
    big.write_bytes(text_of(3 * CHUNK_SIZE + 5))
    assert cli.main(["analyze", str(big)]) == cli.EXIT_OK
    assert capsys.readouterr().err == ""
