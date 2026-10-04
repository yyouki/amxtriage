import gzip

import pytest

from amxtriage.errors import InputError
from amxtriage.follow import LogFollower


class Choreography:
    def __init__(self, steps):
        self._steps = list(steps)
        self.sleep_calls = 0
        self.finished = False

    def sleep(self, _seconds):
        self.sleep_calls += 1
        if self._steps:
            self._steps.pop(0)()
        else:
            self.finished = True

    def should_stop(self):
        return self.finished


def follow(path, steps, **options):
    script = Choreography(steps)
    follower = LogFollower(str(path), sleep=script.sleep, should_stop=script.should_stop, **options)
    return list(follower.lines()), follower, script


def only_lines(items):
    return [item for item in items if item is not None]


def append(path, data):
    def action():
        with path.open("ab") as handle:
            handle.write(data)

    return action


def test_only_lines_written_after_start_are_reported_by_default(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"old one\nold two\n")
    items, _, _ = follow(log, [append(log, b"new one\nnew two\n")])
    assert only_lines(items) == ["new one", "new two"]


def test_from_start_reads_existing_content_first(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"old one\n")
    items, _, _ = follow(log, [append(log, b"new one\n")], from_start=True)
    assert only_lines(items) == ["old one", "new one"]


def test_idle_polls_yield_none_markers_so_pending_blocks_can_be_flushed(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"")
    items, _, script = follow(log, [append(log, b"line\n")])
    assert items == [None, "line", None]
    assert script.sleep_calls == 2


def test_partial_lines_wait_for_their_newline(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"")
    steps = [append(log, b"[13:46:01] [debug] Run time"), append(log, b" error 4\nnext\n")]
    items, _, _ = follow(log, steps)
    assert only_lines(items) == ["[13:46:01] [debug] Run time error 4", "next"]


def test_a_line_split_across_three_polls_is_reassembled(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"")
    steps = [append(log, b"aa"), append(log, b"bb"), append(log, b"cc\n")]
    items, _, _ = follow(log, steps)
    assert only_lines(items) == ["aabbcc"]


def test_rotation_reads_the_new_file_from_its_start(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"before rotation\n")

    def rotate():
        with log.open("ab") as handle:
            handle.write(b"late line in old file\n")
        log.rename(tmp_path / "server_log.txt.1")
        log.write_bytes(b"first in new file\nsecond in new file\n")

    items, _, _ = follow(log, [rotate])
    assert only_lines(items) == ["late line in old file", "first in new file", "second in new file"]


def test_an_unterminated_line_in_the_old_file_is_flushed_on_rotation(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"")

    def write_partial_then_rotate():
        with log.open("ab") as handle:
            handle.write(b"unterminated tail")

    def rotate():
        log.rename(tmp_path / "server_log.txt.1")
        log.write_bytes(b"fresh\n")

    items, _, _ = follow(log, [write_partial_then_rotate, rotate])
    assert only_lines(items) == ["unterminated tail", "fresh"]


def test_truncation_in_place_restarts_from_the_beginning(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"x" * 100 + b"\n")

    def truncate():
        log.write_bytes(b"after truncate\n")

    items, _, _ = follow(log, [truncate], from_start=True)
    assert only_lines(items) == ["x" * 100, "after truncate"]


def test_deleted_and_recreated_file_is_followed(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"one\n")

    def delete():
        log.unlink()

    def recreate():
        log.write_bytes(b"two\n")

    items, _, _ = follow(log, [delete, recreate], from_start=True)
    assert only_lines(items) == ["one", "two"]


def test_overlong_lines_are_truncated_and_counted(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"")
    items, follower, _ = follow(log, [append(log, b"y" * 20000 + b"\nshort\n")])
    assert only_lines(items) == ["y" * 8192, "short"]
    assert follower.truncated_lines == 1


def test_windows_line_endings_are_handled(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"")
    items, _, _ = follow(log, [append(log, b"one\r\ntwo\r\n")])
    assert only_lines(items) == ["one", "two"]


def test_missing_file_is_reported_before_following_starts(tmp_path):
    with pytest.raises(InputError, match="cannot open"):
        list(LogFollower(str(tmp_path / "missing.log")).lines())


def test_directory_is_rejected(tmp_path):
    with pytest.raises(InputError, match="is a directory"):
        list(LogFollower(str(tmp_path)).lines())


def test_compressed_file_is_rejected_with_a_helpful_message(tmp_path):
    log = tmp_path / "rotated.log.gz"
    log.write_bytes(gzip.compress(b"data\n"))
    with pytest.raises(InputError, match="compressed"):
        follow(log, [])


def test_binary_content_is_rejected_when_it_arrives(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"")
    with pytest.raises(InputError, match="binary"):
        follow(log, [append(log, b"\x00\x01\x02 binary")])


def test_should_stop_before_start_yields_nothing_and_closes_the_file(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"data\n")
    follower = LogFollower(str(log), should_stop=lambda: True, from_start=True)
    assert list(follower.lines()) == []
    follower.close()


def test_close_is_idempotent(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"")
    follower = LogFollower(str(log), should_stop=lambda: True)
    list(follower.lines())
    follower.close()
    follower.close()


def test_busy_log_does_not_sleep_between_available_batches(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"\n".join(f"line {n}".encode() for n in range(5000)) + b"\n")
    items, _, script = follow(log, [], from_start=True)
    assert len(only_lines(items)) == 5000
    assert script.sleep_calls == 1
