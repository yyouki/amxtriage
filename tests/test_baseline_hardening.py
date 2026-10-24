import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from amxtriage import baseline as baseline_module
from amxtriage import cli
from amxtriage.baseline import MAX_INTEGER_DIGITS, SCHEMA_VERSION, load_baseline
from amxtriage.errors import BaselineError

VALID_ID = "0123456789ab"
BOM = b"\xef\xbb\xbf"

RunCli = Callable[..., "subprocess.CompletedProcess[bytes]"]


def stored(tmp_path: Path, content: str | bytes) -> str:
    path = tmp_path / "baseline.json"
    path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return str(path)


def document(**changes: object) -> str:
    data: dict[str, object] = {
        "tool": "amxtriage",
        "schema_version": SCHEMA_VERSION,
        "signatures": [{"id": VALID_ID}],
    }
    data.update(changes)
    return json.dumps(data)


def with_extra(literal: str) -> str:
    return '{"tool": "amxtriage", "schema_version": 1, "signatures": [], "extra": ' + literal + "}"


def with_version(literal: str) -> str:
    return '{"tool": "amxtriage", "schema_version": ' + literal + ', "signatures": []}'


def run_main(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.parametrize("digits", [MAX_INTEGER_DIGITS + 1, 4300, 4301, 5001, 200_000])
def test_an_integer_with_too_many_digits_is_a_clean_error(tmp_path: Path, digits: int) -> None:
    with pytest.raises(BaselineError, match="more than 32 digits"):
        load_baseline(stored(tmp_path, with_extra("9" * digits)))


def test_the_digit_limit_is_the_documented_constant() -> None:
    assert MAX_INTEGER_DIGITS == 32


@pytest.mark.parametrize("sign", ["", "-"])
def test_an_integer_of_exactly_the_maximum_digits_is_accepted(tmp_path: Path, sign: str) -> None:
    literal = sign + "9" * MAX_INTEGER_DIGITS
    assert load_baseline(stored(tmp_path, with_extra(literal))) == frozenset()


def test_a_negative_integer_with_one_digit_too_many_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(BaselineError, match="digits"):
        load_baseline(stored(tmp_path, with_extra("-" + "9" * (MAX_INTEGER_DIGITS + 1))))


@pytest.mark.parametrize(
    "text",
    [
        with_version("9" * 5001),
        '{"tool": "amxtriage", "schema_version": 1, "signatures": [{"id": "'
        + VALID_ID
        + '", "count": '
        + "9" * 5001
        + "}]}",
        with_extra("[1, 2, " + "9" * 5001 + "]"),
        with_extra('{"nested": {"deeper": ' + "9" * 5001 + "}}"),
    ],
)
def test_an_oversized_integer_is_rejected_wherever_it_appears(tmp_path: Path, text: str) -> None:
    with pytest.raises(BaselineError, match="digits"):
        load_baseline(stored(tmp_path, text))


@pytest.mark.parametrize(
    "literal",
    [
        "1.5",
        "1e5",
        "-0.0",
        "1e999999999",
        "1" * 5000 + ".5",
        "0." + "0" * 5000 + "1",
        "1E-999999999",
    ],
)
def test_floating_point_numbers_cannot_crash_the_loader(tmp_path: Path, literal: str) -> None:
    assert load_baseline(stored(tmp_path, with_extra(literal))) == frozenset()


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_non_standard_json_constants_are_rejected(tmp_path: Path, literal: str) -> None:
    with pytest.raises(BaselineError, match="non-standard JSON value"):
        load_baseline(stored(tmp_path, with_extra(literal)))


def test_a_utf8_byte_order_mark_is_accepted(tmp_path: Path) -> None:
    path = stored(tmp_path, BOM + document().encode("utf-8"))
    assert load_baseline(path) == frozenset({VALID_ID})


@pytest.mark.parametrize("content", [BOM, BOM + BOM + document().encode("utf-8"), BOM + b" "])
def test_only_one_byte_order_mark_in_front_of_valid_json_is_accepted(
    tmp_path: Path, content: bytes
) -> None:
    with pytest.raises(BaselineError, match="cannot read baseline"):
        load_baseline(stored(tmp_path, content))


def test_a_byte_order_mark_in_the_middle_of_the_text_is_rejected(tmp_path: Path) -> None:
    text = document().replace('"tool"', "\ufeff" + '"tool"')
    with pytest.raises(BaselineError, match="cannot read baseline"):
        load_baseline(stored(tmp_path, text))


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-32"])
def test_baselines_in_other_encodings_are_rejected(tmp_path: Path, encoding: str) -> None:
    with pytest.raises(BaselineError, match="cannot read baseline"):
        load_baseline(stored(tmp_path, document().encode(encoding)))


@pytest.mark.parametrize(
    "literal", ["true", "false", "1.0", "1e0", '"1"', "null", "[1]", '{"v": 1}', "0", "2", "-1"]
)
def test_the_schema_version_must_be_exactly_the_integer_one(tmp_path: Path, literal: str) -> None:
    with pytest.raises(BaselineError, match="unsupported schema_version"):
        load_baseline(stored(tmp_path, with_version(literal)))


def test_a_missing_schema_version_is_unsupported(tmp_path: Path) -> None:
    text = '{"tool": "amxtriage", "signatures": []}'
    with pytest.raises(BaselineError, match="unsupported schema_version"):
        load_baseline(stored(tmp_path, text))


def test_the_schema_version_message_names_a_number_but_not_other_values(tmp_path: Path) -> None:
    with pytest.raises(BaselineError, match=r"schema_version 99; expected 1"):
        load_baseline(stored(tmp_path, with_version("99")))
    with pytest.raises(BaselineError, match=r"schema_version of type str; expected 1"):
        load_baseline(stored(tmp_path, with_version('"99"')))


def test_error_messages_never_echo_values_from_the_file(tmp_path: Path) -> None:
    secret = "TOPSECRETVALUE" * 200
    for text in (
        with_version('"' + secret + '"'),
        document(tool=secret),
        document(signatures=[{"id": secret}]),
        document(signatures=[secret]),
    ):
        with pytest.raises(BaselineError) as caught:
            load_baseline(stored(tmp_path, text))
        assert "TOPSECRETVALUE" not in str(caught.value)
        assert len(str(caught.value)) < 300


@pytest.mark.parametrize("root", ["[]", '"text"', "5", "null", "true", "1.5", "[{}]"])
def test_the_root_of_the_document_must_be_an_object(tmp_path: Path, root: str) -> None:
    with pytest.raises(BaselineError, match="not an amxtriage baseline"):
        load_baseline(stored(tmp_path, root))


@pytest.mark.parametrize(
    "entry", ["null", '"text"', "[]", "1.5", "true", "{}", '{"id": null}', '{"id": ["x"]}']
)
def test_signature_entries_of_the_wrong_type_are_rejected(tmp_path: Path, entry: str) -> None:
    text = '{"tool": "amxtriage", "schema_version": 1, "signatures": [' + entry + "]}"
    with pytest.raises(BaselineError, match="invalid signature id"):
        load_baseline(stored(tmp_path, text))


def test_one_bad_entry_among_valid_ones_rejects_the_whole_file(tmp_path: Path) -> None:
    entries = [{"id": VALID_ID}] * 50 + [{"id": "nothex!nothex"}] + [{"id": VALID_ID}] * 50
    with pytest.raises(BaselineError, match="invalid signature id"):
        load_baseline(stored(tmp_path, document(signatures=entries)))


@pytest.mark.parametrize("opening", ["[", '{"a": '])
def test_deep_nesting_in_an_unused_field_is_a_clean_error(tmp_path: Path, opening: str) -> None:
    closing = "]" if opening == "[" else "}"
    nested = opening * 100_000 + "1" + closing * 100_000
    with pytest.raises(BaselineError, match="cannot read baseline"):
        load_baseline(stored(tmp_path, with_extra(nested)))


def test_moderate_nesting_in_an_unused_field_is_accepted(tmp_path: Path) -> None:
    nested = "[" * 50 + "1" + "]" * 50
    assert load_baseline(stored(tmp_path, with_extra(nested))) == frozenset()


def test_unknown_extra_fields_are_still_tolerated(tmp_path: Path) -> None:
    text = document(future_field={"anything": [1, 2.5, None, "x"]})
    assert load_baseline(stored(tmp_path, text)) == frozenset({VALID_ID})


def test_duplicate_keys_follow_the_last_value_like_other_json_readers(tmp_path: Path) -> None:
    text = (
        '{"tool": "amxtriage", "schema_version": 1, '
        f'"signatures": [{{"id": "{VALID_ID}"}}], "signatures": []}}'
    )
    assert load_baseline(stored(tmp_path, text)) == frozenset()


@pytest.mark.parametrize("limit_offset", [0, -1])
def test_the_size_limit_is_inclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit_offset: int
) -> None:
    text = document()
    path = stored(tmp_path, text)
    monkeypatch.setattr(baseline_module, "MAX_BASELINE_BYTES", len(text) + limit_offset)
    if limit_offset == 0:
        assert load_baseline(path) == frozenset({VALID_ID})
    else:
        with pytest.raises(BaselineError, match="larger than"):
            load_baseline(path)


def test_an_empty_file_is_a_clean_error(tmp_path: Path) -> None:
    with pytest.raises(BaselineError, match="cannot read baseline"):
        load_baseline(stored(tmp_path, b""))


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="needs a POSIX user that file permissions apply to",
)
def test_an_unreadable_baseline_is_a_clean_error(tmp_path: Path) -> None:
    path = Path(stored(tmp_path, document()))
    path.chmod(0)
    try:
        with pytest.raises(BaselineError, match="cannot read baseline"):
            load_baseline(str(path))
    finally:
        path.chmod(0o600)


def test_a_directory_is_a_clean_error(tmp_path: Path) -> None:
    with pytest.raises(BaselineError, match="cannot read baseline"):
        load_baseline(str(tmp_path))


@pytest.mark.parametrize("subcommand", ["analyze", "watch"])
def test_the_cli_reports_an_oversized_integer_as_an_error_not_as_new_problems(
    tmp_path: Path,
    sample_log: Path,
    capsys: pytest.CaptureFixture[str],
    subcommand: str,
) -> None:
    path = stored(tmp_path, with_extra("9" * 5001))
    argv = [subcommand, str(sample_log), "--baseline", path]
    if subcommand == "analyze":
        argv.append("--fail-on-new")
    code, out, err = run_main(argv, capsys)
    assert code == cli.EXIT_ERROR
    assert out == ""
    assert err.startswith("error: ")
    assert "Traceback" not in err
    assert "9" * 100 not in err


def test_a_broken_baseline_is_never_treated_as_a_clean_comparison(
    tmp_path: Path, sample_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for literal in ("true", "1.0", '"1"', "null"):
        path = stored(tmp_path, with_version(literal))
        code, out, _ = run_main(
            ["analyze", str(sample_log), "--baseline", path, "--fail-on-new"], capsys
        )
        assert code == cli.EXIT_ERROR
        assert out == ""


def test_a_byte_order_mark_baseline_works_through_the_cli(
    tmp_path: Path, sample_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saved = tmp_path / "saved.json"
    assert cli.main(["analyze", str(sample_log), "--save-baseline", str(saved)]) == cli.EXIT_OK
    capsys.readouterr()
    marked = tmp_path / "marked.json"
    marked.write_bytes(BOM + saved.read_bytes())
    code, out, err = run_main(
        ["analyze", str(sample_log), "--baseline", str(marked), "--fail-on-new"], capsys
    )
    assert code == cli.EXIT_OK
    assert "0 new problems" in out
    assert err == ""


def test_the_real_process_exits_with_status_two_for_an_oversized_integer(
    tmp_path: Path, sample_log: Path, run_cli: RunCli
) -> None:
    path = stored(tmp_path, with_extra("9" * 5001))
    result = run_cli("analyze", str(sample_log), "--baseline", path, "--fail-on-new")
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"error: ")
    assert b"Traceback" not in result.stderr


def test_python_still_enforces_its_own_digit_limit_so_our_hook_must_run_first() -> None:
    limit_getter = getattr(sys, "get_int_max_str_digits", None)
    if limit_getter is None or limit_getter() == 0:
        pytest.skip("this interpreter has no integer string conversion limit")
    with pytest.raises(ValueError, match="digits"):
        json.loads("9" * (limit_getter() + 1))
