import pytest

from amxtriage.textutil import basename, inline_code, sanitize


def test_sanitize_keeps_plain_text_unchanged():
    assert sanitize("OnPlayerUpdate gamemodes/rp.pwn:30") == "OnPlayerUpdate gamemodes/rp.pwn:30"


def test_sanitize_keeps_unicode_letters():
    assert sanitize("caf\u00e9 \u4e2d\u6587") == "caf\u00e9 \u4e2d\u6587"


@pytest.mark.parametrize(
    "dangerous",
    [
        "\x1b[31mred\x1b[0m",
        "\x1b]0;evil title\x07",
        "null\x00byte",
        "bell\x07",
        "line\nbreak",
        "carriage\rreturn",
        "\x7fdelete",
        "\x9bC1 control",
        "rtl\u202eoverride",
        "isolate\u2066x\u2069",
        "zero\u200bwidth",
        "sep\u2028line",
    ],
)
def test_sanitize_removes_control_and_format_characters(dangerous):
    cleaned = sanitize(dangerous)
    assert all(ord(char) >= 0x20 and ord(char) != 0x7F for char in cleaned)
    assert not any(char in cleaned for char in "\u202e\u2066\u2069\u200b\u2028\x9b")
    assert "?" in cleaned


def test_sanitize_truncates_with_ellipsis():
    cleaned = sanitize("a" * 50, limit=10)
    assert cleaned == "aaaaaaa..."
    assert len(cleaned) == 10


def test_sanitize_does_not_truncate_at_exact_limit():
    assert sanitize("a" * 10, limit=10) == "a" * 10


def test_sanitize_expands_tabs_instead_of_blocking_them():
    assert sanitize("\tx") == "    x"


@pytest.mark.parametrize(
    ("limit", "expected"), [(0, ""), (1, "a"), (2, "ab"), (3, "abc"), (4, "a...")]
)
def test_sanitize_never_exceeds_the_limit_even_when_tiny(limit, expected):
    assert sanitize("abcdefgh", limit=limit) == expected


def test_inline_code_neutralizes_backticks():
    assert inline_code("a`b") == "`a'b`"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("gamemodes/rp.pwn", "rp.pwn"),
        ("C:\\samp\\gamemodes\\rp.pwn", "rp.pwn"),
        ("rp.pwn", "rp.pwn"),
        ("dir/sub/", "sub"),
        ("", ""),
        ("mixed\\and/slashes.inc", "slashes.inc"),
    ],
)
def test_basename_handles_windows_and_posix_paths(path, expected):
    assert basename(path) == expected
