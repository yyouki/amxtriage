import gzip
import threading

import pytest

from amxtriage.errors import InputError
from amxtriage.follow import FollowParser, LogFollower, interruptible_sleep
from amxtriage.reader import CHUNK_SIZE


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


HEADER = '[13:46:01] [debug] Run time error 4: "Array index out of bounds"'
FRAME = (
    "[13:46:01] [debug] #0 000a1b2c in public OnPlayerUpdate (playerid=0) at gamemodes/rp.pwn:30"
)
SCRIPT_LINE = '[13:46:01] Script[gamemodes/rp.amx]: Run time error 4: "Array index out of bounds"'


def fed(parser, lines):
    events = []
    for line in lines:
        events.extend(parser.feed(line))
    return events


def test_a_block_survives_one_quiet_poll_and_is_flushed_by_the_second():
    parser = FollowParser()
    assert fed(parser, [HEADER, "[13:46:01] [debug] AMX backtrace:", FRAME]) == []
    assert parser.idle() == []
    flushed = parser.idle()
    assert [(event.code, event.script, len(event.frames)) for event in flushed] == [(4, None, 1)]


def test_a_script_line_after_one_quiet_poll_is_merged_into_the_block():
    parser = FollowParser()
    fed(parser, [HEADER, "[13:46:01] [debug] AMX backtrace:", FRAME])
    assert parser.idle() == []
    merged = parser.feed(SCRIPT_LINE)
    assert [(event.code, event.script, len(event.frames)) for event in merged] == [
        (4, "gamemodes/rp.amx", 1)
    ]
    assert parser.idle() == []
    assert parser.idle() == []


def test_a_new_line_restarts_the_quiet_count():
    parser = FollowParser()
    fed(parser, [HEADER])
    assert parser.idle() == []
    parser.feed("[13:46:02] unrelated")
    assert parser.idle() == []
    assert len(parser.idle()) == 1


def test_quiet_polls_without_an_open_block_produce_nothing():
    parser = FollowParser()
    for _ in range(5):
        assert parser.idle() == []


def test_the_quiet_count_is_configurable_and_a_single_quiet_poll_can_flush():
    parser = FollowParser(quiet_polls=1)
    fed(parser, [HEADER])
    assert len(parser.idle()) == 1


def test_finish_flushes_immediately_and_line_numbers_follow_the_inner_parser():
    parser = FollowParser()
    fed(parser, [HEADER, FRAME])
    assert parser.line_number == 2
    assert len(parser.finish()) == 1
    assert parser.finish() == []


class FakeEvent(threading.Event):
    def __init__(self, stop_after=None):
        super().__init__()
        self.waits = []
        self._stop_after = stop_after
        self._stopped = False

    def is_set(self):
        return self._stopped

    def wait(self, timeout=None):
        self.waits.append(timeout)
        if self._stop_after is not None and len(self.waits) >= self._stop_after:
            self._stopped = True
        return self._stopped


class FakeClock:
    def __init__(self, event):
        self.now = 0.0
        self._event = event

    def __call__(self):
        if self._event.waits:
            self.now = sum(self._event.waits)
        return self.now


def test_long_sleeps_are_cut_into_short_waits():
    event = FakeEvent()
    sleep = interruptible_sleep(event, slice_seconds=0.25, clock=FakeClock(event))
    assert sleep(1.0) is False
    assert event.waits == [0.25, 0.25, 0.25, 0.25]


def test_the_last_wait_is_only_as_long_as_the_remaining_time():
    event = FakeEvent()
    sleep = interruptible_sleep(event, slice_seconds=0.25, clock=FakeClock(event))
    assert sleep(0.6) is False
    assert event.waits == [0.25, 0.25, pytest.approx(0.1)]


def test_a_stop_request_ends_the_sleep_at_the_next_slice():
    event = FakeEvent(stop_after=2)
    sleep = interruptible_sleep(event, slice_seconds=0.25, clock=FakeClock(event))
    assert sleep(60.0) is True
    assert event.waits == [0.25, 0.25]


def test_a_stop_request_made_before_sleeping_returns_at_once():
    event = threading.Event()
    event.set()
    assert interruptible_sleep(event)(60.0) is True


def test_a_zero_length_sleep_does_not_wait():
    event = FakeEvent()
    assert interruptible_sleep(event, clock=FakeClock(event))(0.0) is False
    assert event.waits == []


def test_a_stop_request_interrupts_the_initial_read_of_a_large_file(tmp_path):
    log = tmp_path / "server_log.txt"
    line = b"x" * 99 + b"\n"
    log.write_bytes(line * ((CHUNK_SIZE * 3) // len(line)))
    calls = []

    def should_stop():
        calls.append(1)
        return len(calls) > 2

    follower = LogFollower(str(log), from_start=True, should_stop=should_stop)
    lines = [item for item in follower.lines() if item is not None]
    assert 0 < len(lines) < (CHUNK_SIZE * 3) // len(line)


def test_bytes_written_to_the_old_file_just_before_rotation_is_detected_are_read(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"")
    backup = tmp_path / "server_log.txt.1"

    class RacingFollower(LogFollower):
        raced = False

        def _replacement(self):
            if not self.raced and log.stat().st_size > 0:
                RacingFollower.raced = True
                with log.open("ab") as handle:
                    handle.write(b"written after the first read\n")
                log.rename(backup)
                log.write_bytes(b"new file\n")
            return super()._replacement()

    script = Choreography([append(log, b"first\n")])
    follower = RacingFollower(str(log), sleep=script.sleep, should_stop=script.should_stop)
    items = list(follower.lines())
    assert only_lines(items) == ["first", "written after the first read", "new file"]


def test_a_file_that_vanishes_while_it_is_being_reopened_is_waited_for(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"one\n")

    class VanishingFollower(LogFollower):
        forced = False

        def _replacement(self):
            if not VanishingFollower.forced and not log.exists():
                VanishingFollower.forced = True
                return "rotated"
            return super()._replacement()

    def delete():
        log.unlink()

    def recreate():
        log.write_bytes(b"two\n")

    script = Choreography([delete, recreate])
    follower = VanishingFollower(
        str(log), from_start=True, sleep=script.sleep, should_stop=script.should_stop
    )
    assert only_lines(list(follower.lines())) == ["one", "two"]


def test_an_unreadable_replacement_file_still_stops_the_watch_with_an_error(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"one\n")

    def rotate():
        log.rename(tmp_path / "server_log.txt.1")
        log.write_bytes(b"new\n")

    script = Choreography([rotate])
    follower = LogFollower(str(log), sleep=script.sleep, should_stop=script.should_stop)
    original_open = follower._open_raw
    open_count = 0

    def deny_replacement():
        nonlocal open_count
        open_count += 1
        if open_count > 1:
            raise PermissionError(13, "Permission denied")
        return original_open()

    monkeypatch.setattr(follower, "_open_raw", deny_replacement)
    with pytest.raises(InputError, match="Permission denied"):
        list(follower.lines())


def test_content_of_a_file_rotated_away_twice_within_one_poll_is_not_read(tmp_path):
    log = tmp_path / "server_log.txt"
    log.write_bytes(b"")

    def rotate_twice():
        with log.open("ab") as handle:
            handle.write(b"first\n")
        log.rename(tmp_path / "server_log.txt.1")
        log.write_bytes(b"skipped middle file\n")
        log.rename(tmp_path / "server_log.txt.2")
        log.write_bytes(b"last file\n")

    items, _, _ = follow(log, [rotate_twice])
    assert only_lines(items) == ["first", "last file"]


def test_a_file_truncated_and_regrown_beyond_the_old_size_within_one_poll_is_not_noticed(tmp_path):
    log = tmp_path / "server_log.txt"
    old = b"old content that is fairly long\n"
    new = b"AAAA new first line\n" + b"BBBB new second line plus padding\n"
    log.write_bytes(old)

    def truncate_and_regrow():
        log.write_bytes(new)

    items, _, _ = follow(log, [truncate_and_regrow], from_start=True)
    resumed = new[len(old) :].rstrip(b"\n").decode()
    assert only_lines(items) == [old.rstrip(b"\n").decode(), resumed]
    assert resumed != "BBBB new second line plus padding"
