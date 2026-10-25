import pytest

from amxtriage import cli


def run_explain(argument: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = cli.main(["explain", argument])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.parametrize(
    "argument",
    [
        "\u00b2",
        "-1",
        "1e3",
        " ",
        "0x13",
        "1.5",
        "nineteen",
        "7" * 5000,
        "\u0663" * 5000,
        "\x1b[31m",
        "\u202e19",
    ],
)
def test_unusual_error_codes_are_usage_errors_without_a_traceback(
    argument: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(["explain", argument])
    assert caught.value.code == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "\x1b" not in err
    assert "\u202e" not in err


def test_a_huge_but_valid_number_is_an_unknown_code_with_a_bounded_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_explain("7" * 4000, capsys)
    assert code == cli.EXIT_ERROR
    assert out == ""
    assert err.startswith("error: unknown AMX error code 777")
    assert len(err) < cli.MESSAGE_LIMIT + 100


@pytest.mark.parametrize("argument", ["\u0661\u0669", " 19 ", "19\n", "+19", "0019"])
def test_other_spellings_of_the_same_number_give_the_same_answer(
    argument: str, capsys: pytest.CaptureFixture[str]
) -> None:
    plain = run_explain("19", capsys)
    other = run_explain(argument, capsys)
    assert plain[0] == other[0] == cli.EXIT_OK
    assert plain[1] == other[1]
    assert "19" in plain[1]
