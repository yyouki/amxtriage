import argparse
import contextlib
import glob
import os
import re
import signal
import sys
import threading
import traceback
from collections.abc import Callable, Sequence
from pathlib import Path
from types import FrameType

from amxtriage import __version__
from amxtriage.aggregate import Aggregator
from amxtriage.amxerrors import lookup
from amxtriage.analysis import AnalysisResult, analyze_logs, build_report, snippet_for
from amxtriage.baseline import load_baseline, save_baseline
from amxtriage.errors import AmxTriageError, InputError
from amxtriage.follow import (
    DEFAULT_POLL_INTERVAL,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    FollowParser,
    LogFollower,
    interruptible_sleep,
)
from amxtriage.model import REPORTED_KINDS, Event, EventKind
from amxtriage.localization import SUPPORTED_LANGUAGES, translate as tr
from amxtriage.output import write_text_file
from amxtriage.reader import STDIN_NAME, display_name
from amxtriage.recommendation import render_recommendations
from amxtriage.render import (
    FORMATS,
    render_error_list,
    render_explain,
    render_group_text,
    render_report,
)
from amxtriage.source import MAX_CONTEXT_RADIUS, SourceIndex
from amxtriage.textutil import basename, sanitize

EXIT_OK = 0
EXIT_NEW_PROBLEMS = 1
EXIT_ERROR = 2
EXIT_INTERRUPTED = 130

MESSAGE_LIMIT = 1000
INTERNAL_ERROR_FRAMES = 5

DEFAULT_TOP = 20
DEFAULT_CONTEXT = 3
WATCH_SUMMARY_TOP = 20
WILDCARD_CHARACTERS = "*?["

ARGS_WARNING = (
    "Include function arguments in backtraces. Arguments can contain text typed by players, "
    "such as passwords, so do not share the output."
)


def _bounded_int(minimum: int, maximum: int | None = None) -> Callable[[str], int]:
    def convert(text: str) -> int:
        try:
            value = int(text)
        except ValueError as error:
            raise argparse.ArgumentTypeError(f"invalid integer: {text!r}") from error
        if value < minimum or (maximum is not None and value > maximum):
            limit = f"at least {minimum}" if maximum is None else f"between {minimum} and {maximum}"
            raise argparse.ArgumentTypeError(f"must be {limit}")
        return value

    return convert


_SIZE = re.compile(r"(\d{1,15})([KMGkmg]?)")
_SIZE_UNITS = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3}


def _size(text: str) -> int:
    match = _SIZE.fullmatch(text.strip())
    if match is None:
        raise argparse.ArgumentTypeError(
            f"invalid size: {text!r} (use a number of bytes, or a number followed by K, M or G)"
        )
    return int(match[1]) * _SIZE_UNITS[match[2].upper()]


def _poll_interval(text: str) -> float:
    try:
        value = float(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid number: {text!r}") from error
    if not MIN_POLL_INTERVAL <= value <= MAX_POLL_INTERVAL:
        raise argparse.ArgumentTypeError(
            f"must be between {MIN_POLL_INTERVAL} and {MAX_POLL_INTERVAL} seconds"
        )
    return value


def _add_context_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--source-dir",
        metavar="DIR",
        help="folder with your .pwn/.inc files; shows the source lines around each problem",
    )
    command.add_argument(
        "--context",
        type=_bounded_int(0, MAX_CONTEXT_RADIUS),
        default=DEFAULT_CONTEXT,
        metavar="N",
        help="source lines shown above and below the problem line "
        f"(default {DEFAULT_CONTEXT}, 0 disables)",
    )
    command.add_argument("--show-args", action="store_true", help=ARGS_WARNING)
    command.add_argument(
        "--baseline",
        metavar="FILE",
        help="baseline JSON file; problems already listed in it are hidden",
    )


def _add_language_argument(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--language", "--lang", choices=SUPPORTED_LANGUAGES, default=argparse.SUPPRESS,
        help=tr("en", "language_help"),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="amxtriage",
        description="Triage SA-MP and open.mp server logs: groups AMX runtime errors, "
        "crashes and slow callbacks reported by the crashdetect plugin.",
    )
    parser.add_argument("--version", action="version", version=f"amxtriage {__version__}")
    parser.add_argument(
        "--language", "--lang", choices=SUPPORTED_LANGUAGES, default="en",
        help=tr("en", "language_help"),
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    analyze = commands.add_parser(
        "analyze",
        help="analyze one or more log files and print a report",
        description="Analyze log files (plain text or .gz; use '-' for stdin). "
        "Pass rotated files oldest first.",
    )
    _add_language_argument(analyze)
    analyze.add_argument("logs", nargs="+", metavar="LOG", help="log file(s) to analyze")
    analyze.add_argument("--format", choices=FORMATS, default="text", help="report format")
    analyze.add_argument("-o", "--output", metavar="FILE", help="write the report to FILE (UTF-8)")
    analyze.add_argument(
        "--top",
        type=_bounded_int(1),
        default=DEFAULT_TOP,
        metavar="N",
        help=f"maximum problems shown (default {DEFAULT_TOP})",
    )
    analyze.add_argument(
        "--min-count",
        type=_bounded_int(1),
        default=1,
        metavar="N",
        help="hide problems that occurred fewer than N times",
    )
    analyze.add_argument(
        "--kind",
        action="append",
        choices=REPORTED_KINDS,
        dest="kinds",
        help="only show this kind of problem (repeatable)",
    )
    analyze.add_argument(
        "--max-input-bytes",
        type=_size,
        default=0,
        metavar="SIZE",
        help="stop with an error if an input has more than SIZE bytes after decompression "
        "(plain number, or with K, M or G; 0 means no limit, which is the default)",
    )
    analyze.add_argument(
        "--save-baseline",
        metavar="FILE",
        help="write every problem found in this run to FILE for later comparison",
    )
    analyze.add_argument(
        "--fail-on-new",
        action="store_true",
        help="exit with status 1 if problems not in the baseline are found (needs --baseline)",
    )
    _add_context_arguments(analyze)

    watch = commands.add_parser(
        "watch",
        help="follow a live log and print each new kind of problem once",
        description="Follow a growing log file. Each new problem signature is printed once; "
        "a summary is printed when you press Ctrl+C.",
    )
    _add_language_argument(watch)
    watch.add_argument("log", metavar="LOG", help="log file to follow")
    watch.add_argument("--from-start", action="store_true", help="read the existing content first")
    watch.add_argument(
        "--poll-interval",
        type=_poll_interval,
        default=DEFAULT_POLL_INTERVAL,
        metavar="SECONDS",
        help=f"seconds between checks for new lines (default {DEFAULT_POLL_INTERVAL})",
    )
    _add_context_arguments(watch)

    recommend = commands.add_parser(
        "recommend",
        aliases=["suggest"],
        help="recommend debugging steps and illustrative Pawn patterns for log problems",
        description=(
            "Generate offline, rule-based remediation advice. This command never edits source "
            "files; examples are templates that must be adapted and tested."
        ),
    )
    _add_language_argument(recommend)
    recommend.add_argument("logs", nargs="+", metavar="LOG", help="log file(s) to analyze")
    recommend.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    recommend.add_argument("-o", "--output", metavar="FILE", help="write recommendations to FILE")
    recommend.add_argument(
        "--top",
        type=_bounded_int(1),
        default=DEFAULT_TOP,
        metavar="N",
        help=f"maximum problems to recommend for (default {DEFAULT_TOP})",
    )
    recommend.add_argument(
        "--min-count",
        type=_bounded_int(1),
        default=1,
        metavar="N",
        help="hide problems that occurred fewer than N times",
    )
    recommend.add_argument(
        "--max-input-bytes",
        type=_size,
        default=0,
        metavar="SIZE",
        help="stop if an input exceeds SIZE after decompression (0 means no limit)",
    )
    recommend.add_argument(
        "--source-dir",
        metavar="DIR",
        help="folder with your .pwn/.inc files; adds matching source context",
    )
    recommend.add_argument(
        "--context",
        type=_bounded_int(0, MAX_CONTEXT_RADIUS),
        default=DEFAULT_CONTEXT,
        metavar="N",
        help=f"source lines shown above and below the problem line (default {DEFAULT_CONTEXT})",
    )

    explain = commands.add_parser(
        "explain",
        help="explain an AMX runtime error code (no code lists all known codes)",
    )
    _add_language_argument(explain)
    explain.add_argument("code", nargs="?", type=_bounded_int(0), metavar="CODE")
    return parser


def expand_paths(paths: Sequence[str]) -> list[str]:
    expanded: list[str] = []
    for path in paths:
        has_wildcard = any(character in path for character in WILDCARD_CHARACTERS)
        if path != STDIN_NAME and has_wildcard and not Path(path).exists():
            matches = sorted(glob.glob(path))
            if not matches:
                raise InputError(f"no files match '{path}'")
            expanded.extend(matches)
        else:
            expanded.append(path)
    return expanded


def _write_output(text: str, output: str | None) -> None:
    if output is None:
        sys.stdout.write(text)
        sys.stdout.flush()
        return
    write_text_file(output, text)


def _run_analyze(args: argparse.Namespace) -> int:
    baseline = load_baseline(args.baseline) if args.baseline else None
    source_index = SourceIndex(args.source_dir) if args.source_dir else None
    kinds: list[EventKind] | None = list(dict.fromkeys(args.kinds)) if args.kinds else None
    result = analyze_logs(expand_paths(args.logs), max_input_bytes=args.max_input_bytes or None)
    report = build_report(
        result,
        top=args.top,
        min_count=args.min_count,
        kinds=kinds,
        baseline=baseline,
        source_index=source_index,
        context_radius=args.context,
    )
    _write_output(render_report(report, args.format, show_args=args.show_args, language=args.language), args.output)
    if args.save_baseline:
        saved = save_baseline(args.save_baseline, result.aggregator.sorted_groups())
        target = sanitize(args.save_baseline, MESSAGE_LIMIT)
        print(f"saved baseline with {saved} signature(s) to {target}", file=sys.stderr)
    if args.fail_on_new and report.matching_groups > 0:
        return EXIT_NEW_PROBLEMS
    return EXIT_OK


def _install_sigterm(stop: threading.Event) -> Callable[[], None]:
    def handler(_signal_number: int, _frame: FrameType | None) -> None:
        stop.set()

    try:
        previous = signal.signal(signal.SIGTERM, handler)
    except ValueError:
        return lambda: None

    def restore() -> None:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)

    return restore


def _announce_new_problem(
    event: Event,
    aggregator: Aggregator,
    label: str,
    baseline: frozenset[str] | None,
    source_index: SourceIndex | None,
    args: argparse.Namespace,
) -> None:
    added = aggregator.add(event, label)
    group = added.group
    if group is None or not added.created:
        return
    if baseline is not None and group.signature_id in baseline:
        return
    snippet = None
    if source_index is not None and args.context > 0:
        snippet = snippet_for(group, source_index, args.context)
    lines = render_group_text(group, show_args=args.show_args, snippet=snippet, new=True, language=args.language)
    print("\n".join(lines) + "\n", flush=True)


def _run_watch(args: argparse.Namespace) -> int:
    baseline = load_baseline(args.baseline) if args.baseline else None
    source_index = SourceIndex(args.source_dir) if args.source_dir else None
    stop = threading.Event()
    follower = LogFollower(
        args.log,
        from_start=args.from_start,
        poll_interval=args.poll_interval,
        sleep=interruptible_sleep(stop),
        should_stop=stop.is_set,
    )
    parser = FollowParser()
    aggregator = Aggregator()
    label = display_name(args.log)
    restore_signal = _install_sigterm(stop)
    print(
        tr(args.language, "watching").format(
            label=sanitize(label, MESSAGE_LIMIT), interval=f"{args.poll_interval:g}"
        ),
        file=sys.stderr,
        flush=True,
    )
    try:
        for item in follower.lines():
            events = parser.idle() if item is None else parser.feed(item)
            for event in events:
                _announce_new_problem(event, aggregator, label, baseline, source_index, args)
    except KeyboardInterrupt:
        pass
    finally:
        restore_signal()
        follower.close()
    for event in parser.finish():
        _announce_new_problem(event, aggregator, label, baseline, source_index, args)
    result = AnalysisResult([label], parser.line_number, follower.truncated_lines, aggregator)
    report = build_report(
        result,
        top=WATCH_SUMMARY_TOP,
        baseline=baseline,
        source_index=source_index,
        context_radius=0,
    )
    _write_output(tr(args.language, "watch_summary") + "\n" + render_report(report, "text", show_args=args.show_args, language=args.language), None)
    return EXIT_OK


def _run_recommend(args: argparse.Namespace) -> int:
    source_index = SourceIndex(args.source_dir) if args.source_dir else None
    result = analyze_logs(expand_paths(args.logs), max_input_bytes=args.max_input_bytes or None)
    report = build_report(
        result,
        top=args.top,
        min_count=args.min_count,
        source_index=source_index,
        context_radius=args.context,
    )
    _write_output(render_recommendations(report, args.format, language=args.language), args.output)
    return EXIT_OK


def _run_explain(args: argparse.Namespace) -> int:
    if args.code is None:
        _write_output(render_error_list(args.language), None)
        return EXIT_OK
    error = lookup(args.code)
    if error is None:
        raise AmxTriageError(
            tr(args.language, "unknown_code").format(code=args.code)
        )
    _write_output(render_explain(error, args.language), None)
    return EXIT_OK


def _configure_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")


def _silence_stdout() -> None:
    with contextlib.suppress(OSError, ValueError):
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def _internal_error_lines(error: Exception) -> list[str]:
    label = type(error).__name__
    if isinstance(error, OSError) and error.strerror:
        label = f"{label}: {error.strerror}"
    lines = [f"error: internal error ({sanitize(label, 200)}); please report this as a bug"]
    for frame in traceback.extract_tb(error.__traceback__)[-INTERNAL_ERROR_FRAMES:]:
        place = f"{basename(frame.filename)}:{frame.lineno} in {frame.name}"
        lines.append(f"  at {sanitize(place, 200)}")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    _configure_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "analyze" and args.fail_on_new and not args.baseline:
        parser.error("--fail-on-new requires --baseline")
    try:
        if args.command == "analyze":
            return _run_analyze(args)
        if args.command == "watch":
            return _run_watch(args)
        if args.command in ("recommend", "suggest"):
            return _run_recommend(args)
        return _run_explain(args)
    except AmxTriageError as error:
        print(f"error: {sanitize(str(error), MESSAGE_LIMIT)}", file=sys.stderr)
        return EXIT_ERROR
    except BrokenPipeError:
        _silence_stdout()
        return EXIT_OK
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    except Exception as error:
        print("\n".join(_internal_error_lines(error)), file=sys.stderr)
        return EXIT_ERROR
