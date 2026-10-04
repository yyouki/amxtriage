import gzip
import io
import sys

import pytest

from amxtriage.errors import InputError
from amxtriage.reader import (
    LineSplitter,
    check_text_like,
    display_name,
    iter_lines,
    open_log,
)


def split_all(chunks, max_line_bytes=8192):
    splitter = LineSplitter(max_line_bytes)
    lines = []
    for chunk in chunks:
        lines.extend(splitter.feed(chunk))
    lines.extend(splitter.finish())
    return lines, splitter


def read_path(path):
    splitter = LineSplitter()
    with open_log(str(path)) as stream:
        return list(iter_lines(stream, splitter, str(path))), splitter


def test_splits_simple_lines_and_counts_them():
    lines, splitter = split_all([b"one\ntwo\nthree\n"])
    assert lines == ["one", "two", "three"]
    assert splitter.lines == 3
    assert splitter.truncated == 0


def test_last_line_without_newline_is_returned_by_finish():
    lines, _ = split_all([b"one\ntwo"])
    assert lines == ["one", "two"]


def test_empty_lines_are_preserved():
    lines, _ = split_all([b"a\n\nb\n"])
    assert lines == ["a", "", "b"]


def test_crlf_line_endings_are_stripped():
    lines, _ = split_all([b"one\r\ntwo\r\n"])
    assert lines == ["one", "two"]


def test_line_split_across_many_chunks_is_reassembled():
    lines, _ = split_all([b"he", b"ll", b"o wo", b"rld\nsec", b"ond\n"])
    assert lines == ["hello world", "second"]


def test_utf8_bom_is_removed_from_the_first_line_only():
    lines, _ = split_all([b"\xef\xbb\xbf[13:00:00] first\n[13:00:01] second\n"])
    assert lines == ["[13:00:00] first", "[13:00:01] second"]


def test_invalid_utf8_is_replaced_instead_of_failing():
    lines, _ = split_all([b"bad \xff\xfe bytes\n"])
    assert lines == ["bad \ufffd\ufffd bytes"]


def test_overlong_line_is_truncated_and_counted_once():
    lines, splitter = split_all([b"x" * 100 + b"\nnext\n"], max_line_bytes=10)
    assert lines == ["x" * 10, "next"]
    assert splitter.truncated == 1


def test_overlong_line_spanning_chunks_discards_the_remainder():
    chunks = [b"a" * 8, b"b" * 8, b"c" * 8 + b"\nshort\n"]
    lines, splitter = split_all(chunks, max_line_bytes=10)
    assert lines == ["aaaaaaaabb", "short"]
    assert splitter.truncated == 1


def test_overlong_final_line_without_newline_is_truncated():
    lines, splitter = split_all([b"z" * 50], max_line_bytes=10)
    assert lines == ["z" * 10]
    assert splitter.truncated == 1


def test_line_of_exactly_the_maximum_size_is_not_truncated():
    lines, splitter = split_all([b"y" * 10 + b"\n"], max_line_bytes=10)
    assert lines == ["y" * 10]
    assert splitter.truncated == 0


def test_huge_single_line_keeps_memory_bounded():
    splitter = LineSplitter(max_line_bytes=1024)
    produced = []
    for _ in range(200):
        produced.extend(splitter.feed(b"q" * 65536))
    produced.extend(splitter.finish())
    assert produced == ["q" * 1024]
    assert splitter.truncated == 1


def test_finish_is_idempotent_and_resets_state():
    splitter = LineSplitter()
    splitter.feed(b"partial")
    assert splitter.finish() == ["partial"]
    assert splitter.finish() == []
    assert splitter.feed(b"fresh\n") == ["fresh"]


def test_empty_input_produces_no_lines():
    lines, splitter = split_all([b""])
    assert lines == []
    assert splitter.lines == 0


def test_open_log_reads_a_plain_file(tmp_path):
    path = tmp_path / "server_log.txt"
    path.write_bytes(b"alpha\nbeta\n")
    lines, _ = read_path(path)
    assert lines == ["alpha", "beta"]


def test_open_log_reads_gzip_by_content_not_by_extension(tmp_path):
    path = tmp_path / "rotated.log.1"
    path.write_bytes(gzip.compress(b"compressed one\ncompressed two\n"))
    lines, _ = read_path(path)
    assert lines == ["compressed one", "compressed two"]


def test_corrupt_gzip_raises_input_error(tmp_path):
    path = tmp_path / "broken.gz"
    good = gzip.compress(b"line\n" * 5000)
    path.write_bytes(good[: len(good) // 2])
    with pytest.raises(InputError, match="failed while reading"):
        read_path(path)


def test_missing_file_raises_input_error_with_path(tmp_path):
    missing = tmp_path / "nope.txt"
    with pytest.raises(InputError, match="cannot open"):
        read_path(missing)


def test_directory_raises_input_error(tmp_path):
    with pytest.raises(InputError, match="is a directory"):
        read_path(tmp_path)


def test_binary_file_is_rejected_with_clear_message(tmp_path):
    path = tmp_path / "gamemode.amx"
    path.write_bytes(b"\x00\x01\x02binary\x00data")
    with pytest.raises(InputError, match="binary"):
        read_path(path)


@pytest.mark.parametrize("bom", [b"\xff\xfe", b"\xfe\xff"])
def test_utf16_logs_are_rejected_with_actionable_message(tmp_path, bom):
    path = tmp_path / "utf16.log"
    path.write_bytes(bom + "[13:00:00] hi\n".encode("utf-16-le"))
    with pytest.raises(InputError, match="UTF-16"):
        read_path(path)


def test_stdin_is_supported(monkeypatch):
    stdin = io.TextIOWrapper(io.BytesIO(b"from stdin\nsecond\n"), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", stdin)
    splitter = LineSplitter()
    with open_log("-") as stream:
        assert list(iter_lines(stream, splitter, "-")) == ["from stdin", "second"]


def test_display_name_uses_basename_and_stdin_label():
    assert display_name("/var/log/samp/server_log.txt") == "server_log.txt"
    assert display_name("-") == "<stdin>"


def test_check_text_like_accepts_text_and_rejects_nul():
    check_text_like(b"plain text", "x")
    with pytest.raises(InputError):
        check_text_like(b"a\x00b", "x")
