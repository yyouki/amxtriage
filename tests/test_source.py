import os

import pytest

from amxtriage import source as source_module
from amxtriage.errors import SourceError
from amxtriage.source import SourceIndex, path_components


def make_tree(root, files):
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


NUMBERED = "\n".join(f"line {number}" for number in range(1, 101)) + "\n"


@pytest.mark.parametrize(
    ("logged", "expected"),
    [
        ("gamemodes/rp.pwn", ["gamemodes", "rp.pwn"]),
        ("C:\\samp\\gamemodes\\rp.pwn", ["samp", "gamemodes", "rp.pwn"]),
        ("../../etc/passwd", ["etc", "passwd"]),
        ("./a/./b.pwn", ["a", "b.pwn"]),
        ("//double//slashes//x.inc", ["double", "slashes", "x.inc"]),
        ("", []),
        ("..", []),
    ],
)
def test_path_components_drops_drive_dots_and_empty_parts(logged, expected):
    assert path_components(logged) == expected


def test_finds_file_by_basename_when_unique(tmp_path):
    make_tree(tmp_path, {"modules/player.pwn": NUMBERED})
    found = SourceIndex(str(tmp_path)).find("C:\\build\\gamemodes\\player.pwn")
    assert found == (tmp_path / "modules" / "player.pwn").resolve()


def test_matching_is_case_insensitive(tmp_path):
    make_tree(tmp_path, {"Player.pwn": NUMBERED})
    assert SourceIndex(str(tmp_path)).find("gamemodes/PLAYER.PWN") is not None


def test_longest_matching_path_suffix_wins_between_same_named_files(tmp_path):
    make_tree(tmp_path, {"gamemodes/main.pwn": NUMBERED, "filterscripts/main.pwn": NUMBERED})
    index = SourceIndex(str(tmp_path))
    assert (
        index.find("/srv/x/filterscripts/main.pwn")
        == (tmp_path / "filterscripts" / "main.pwn").resolve()
    )
    assert index.find("gamemodes/main.pwn") == (tmp_path / "gamemodes" / "main.pwn").resolve()


def test_ambiguous_basename_matches_nothing(tmp_path):
    make_tree(tmp_path, {"a/main.pwn": NUMBERED, "b/main.pwn": NUMBERED})
    assert SourceIndex(str(tmp_path)).find("main.pwn") is None
    assert SourceIndex(str(tmp_path)).find("/elsewhere/main.pwn") is None


def test_unknown_file_and_wrong_suffix_match_nothing(tmp_path):
    make_tree(tmp_path, {"notes.txt": "x", "real.pwn": NUMBERED})
    index = SourceIndex(str(tmp_path))
    assert index.find("gamemodes/other.pwn") is None
    assert index.find("notes.txt") is None
    assert index.file_count == 1


def test_snippet_returns_target_and_surrounding_lines(tmp_path):
    make_tree(tmp_path, {"rp.pwn": NUMBERED})
    snippet = SourceIndex(str(tmp_path)).snippet("gamemodes/rp.pwn", 50, 2)
    assert snippet is not None
    assert (snippet.path, snippet.first_line, snippet.target_line) == ("rp.pwn", 48, 50)
    assert snippet.lines == ("line 48", "line 49", "line 50", "line 51", "line 52")


def test_snippet_near_the_start_of_the_file_is_clamped(tmp_path):
    make_tree(tmp_path, {"rp.pwn": NUMBERED})
    snippet = SourceIndex(str(tmp_path)).snippet("rp.pwn", 1, 3)
    assert snippet is not None
    assert snippet.first_line == 1
    assert snippet.lines == ("line 1", "line 2", "line 3", "line 4")


def test_snippet_near_the_end_of_the_file_is_clamped(tmp_path):
    make_tree(tmp_path, {"rp.pwn": NUMBERED})
    snippet = SourceIndex(str(tmp_path)).snippet("rp.pwn", 100, 3)
    assert snippet is not None
    assert snippet.lines[-1] == "line 100"


def test_line_beyond_end_of_file_yields_no_snippet(tmp_path):
    make_tree(tmp_path, {"rp.pwn": NUMBERED})
    assert SourceIndex(str(tmp_path)).snippet("rp.pwn", 101, 3) is None


@pytest.mark.parametrize(("line", "radius"), [(0, 3), (-5, 3), (10, 0), (10, -1)])
def test_invalid_line_or_radius_yields_no_snippet(tmp_path, line, radius):
    make_tree(tmp_path, {"rp.pwn": NUMBERED})
    assert SourceIndex(str(tmp_path)).snippet("rp.pwn", line, radius) is None


def test_radius_is_clamped_to_the_maximum(tmp_path):
    make_tree(tmp_path, {"rp.pwn": "\n".join(f"l{n}" for n in range(1, 500)) + "\n"})
    snippet = SourceIndex(str(tmp_path)).snippet("rp.pwn", 250, 10_000)
    assert snippet is not None
    assert len(snippet.lines) == 2 * source_module.MAX_CONTEXT_RADIUS + 1


def test_control_characters_in_source_lines_are_neutralized(tmp_path):
    make_tree(tmp_path, {"rp.pwn": "ok\n\x1b[31mred\x1b[0m\tand tab\n"})
    snippet = SourceIndex(str(tmp_path)).snippet("rp.pwn", 2, 1)
    assert snippet is not None
    assert "\x1b" not in snippet.lines[1]
    assert snippet.lines[1].startswith("?[31mred")


def test_very_long_source_lines_are_truncated(tmp_path):
    make_tree(tmp_path, {"rp.pwn": "x" * 5000 + "\n"})
    snippet = SourceIndex(str(tmp_path)).snippet("rp.pwn", 1, 1)
    assert snippet is not None
    assert len(snippet.lines[0]) == source_module.MAX_SOURCE_LINE_CHARS


def test_non_utf8_source_is_decoded_leniently(tmp_path):
    (tmp_path / "rp.pwn").write_bytes(b"caf\xe9 line\n")
    snippet = SourceIndex(str(tmp_path)).snippet("rp.pwn", 1, 1)
    assert snippet is not None
    assert "line" in snippet.lines[0]


def test_log_path_traversal_cannot_reach_files_outside_the_source_dir(tmp_path):
    outside = tmp_path / "secret.pwn"
    outside.write_text("TOP SECRET\n")
    root = tmp_path / "src"
    make_tree(root, {"rp.pwn": NUMBERED})
    index = SourceIndex(str(root))
    for hostile in ("../secret.pwn", "../../secret.pwn", str(outside), "..\\secret.pwn"):
        snippet = index.snippet(hostile, 1, 1)
        assert snippet is None or "TOP SECRET" not in "".join(snippet.lines)


def test_absolute_system_paths_in_logs_never_select_system_files(tmp_path):
    make_tree(tmp_path, {"rp.pwn": NUMBERED})
    index = SourceIndex(str(tmp_path))
    for hostile in ("/etc/passwd", "C:\\Windows\\win.ini", "/proc/self/environ"):
        assert index.snippet(hostile, 1, 1) is None


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are not available")
def test_symlink_pointing_outside_the_source_dir_is_refused(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("TOP SECRET\n")
    root = tmp_path / "src"
    root.mkdir()
    try:
        (root / "evil.pwn").symlink_to(outside)
    except OSError:
        pytest.skip("cannot create symlinks here")
    index = SourceIndex(str(root))
    assert index.find("evil.pwn") is None
    assert index.snippet("evil.pwn", 1, 1) is None


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are not available")
def test_symlink_pointing_inside_the_source_dir_is_allowed(tmp_path):
    make_tree(tmp_path, {"real/rp.pwn": NUMBERED})
    try:
        (tmp_path / "alias.pwn").symlink_to(tmp_path / "real" / "rp.pwn")
    except OSError:
        pytest.skip("cannot create symlinks here")
    assert SourceIndex(str(tmp_path)).find("alias.pwn") is not None


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are not available")
def test_symlinked_directories_are_not_followed_during_indexing(tmp_path):
    outside = tmp_path / "outside"
    make_tree(outside, {"leak.pwn": NUMBERED})
    root = tmp_path / "src"
    root.mkdir()
    try:
        (root / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create symlinks here")
    assert SourceIndex(str(root)).find("leak.pwn") is None


def test_oversized_source_files_are_ignored(tmp_path, monkeypatch):
    make_tree(tmp_path, {"rp.pwn": NUMBERED})
    monkeypatch.setattr(source_module, "MAX_SOURCE_BYTES", 10)
    assert SourceIndex(str(tmp_path)).snippet("rp.pwn", 1, 1) is None


def test_missing_source_directory_raises_source_error(tmp_path):
    with pytest.raises(SourceError, match="cannot be used"):
        SourceIndex(str(tmp_path / "nope"))


def test_source_directory_that_is_a_file_raises_source_error(tmp_path):
    target = tmp_path / "file.pwn"
    target.write_text("x")
    with pytest.raises(SourceError, match="not a directory"):
        SourceIndex(str(target))


def test_scan_stops_when_too_many_source_files_exist(tmp_path, monkeypatch):
    make_tree(tmp_path, {f"f{n}.pwn": "x" for n in range(5)})
    monkeypatch.setattr(source_module, "MAX_INDEXED_FILES", 3)
    with pytest.raises(SourceError, match="source files"):
        SourceIndex(str(tmp_path))


def test_scan_stops_when_too_many_directories_exist(tmp_path, monkeypatch):
    for number in range(6):
        (tmp_path / f"d{number}").mkdir()
    monkeypatch.setattr(source_module, "MAX_SCANNED_DIRECTORIES", 3)
    with pytest.raises(SourceError, match="sub-directories"):
        SourceIndex(str(tmp_path))


def test_version_control_and_dependency_directories_are_skipped(tmp_path):
    make_tree(tmp_path, {".git/hooks/x.pwn": "x", "node_modules/y.pwn": "x", "real.pwn": NUMBERED})
    assert SourceIndex(str(tmp_path)).file_count == 1
