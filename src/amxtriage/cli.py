import argparse
import contextlib
import glob
import os
import re
import signal
import sys
import threading
import time
import traceback
from collections.abc import Callable, Sequence
from pathlib import Path
from types import FrameType

from amxtriage import __version__
from amxtriage.aggregate import Aggregator
from amxtriage.alerts import (
    DEFAULT_ALERT_MESSAGE_TEMPLATE,
    DEFAULT_ALERT_PREFIX,
    DEFAULT_ALERT_TEMPLATE,
    AlertThrottle,
    JsonlAlertSink,
    PawnBridgeAlertSink,
)
from amxtriage.amxerrors import lookup
from amxtriage.analysis import AnalysisResult, analyze_logs, build_report, snippet_for
from amxtriage.baseline import load_baseline, save_baseline
from amxtriage.compiler import (
    COMPILER_LANGUAGES,
    analyze_compiler_outputs,
    render_compiler_report,
)
from amxtriage.errors import AmxTriageError, InputError
from amxtriage.fixes import apply_patch_preview, build_patch_preview, render_patch_preview
from amxtriage.follow import (
    DEFAULT_POLL_INTERVAL,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    FollowParser,
    LogFollower,
    interruptible_sleep,
)
from amxtriage.localization import SUPPORTED_LANGUAGES
from amxtriage.localization import translate as tr
from amxtriage.model import REPORTED_KINDS, Event, EventKind
from amxtriage.monitoring import (
    DEFAULT_METRICS_INTERVAL_SECONDS,
    JsonlMetricsSink,
    MetricsSampler,
    metrics_supported,
)
from amxtriage.output import write_text_file
from amxtriage.plugin_catalog import (
    KINDS,
    STATUSES,
    filter_catalog_entries,
    load_catalog,
    render_catalog_report,
)
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
EXIT_NO_PATCH = 3

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


def _sha256_digest(text: str) -> str:
    if re.fullmatch(r"[0-9a-fA-F]{64}", text) is None:
        raise argparse.ArgumentTypeError(
            "must be a 64-character SHA-256 hex digest copied from patch-preview"
        )
    return text.lower()


def _size(text: str) -> int:
    match = _SIZE.fullmatch(text.strip())
    if match is None:
        raise argparse.ArgumentTypeError(
            f"invalid size: {text!r} (use a number of bytes, or a number followed by K, M or G)"
        )
    return int(match[1]) * _SIZE_UNITS[match[2].upper()]


def _alert_cooldown(text: str) -> float:
    try:
        value = float(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid number: {text!r}") from error
    if not 0.0 <= value <= 86400.0:
        raise argparse.ArgumentTypeError("must be between 0 and 86400 seconds")
    return value


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


def _metrics_interval(text: str) -> float:
    try:
        value = float(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid number: {text!r}") from error
    if not 1.0 <= value <= 3600.0:
        raise argparse.ArgumentTypeError("must be between 1 and 3600 seconds")
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
        "--language",
        "--lang",
        choices=SUPPORTED_LANGUAGES,
        default=argparse.SUPPRESS,
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
        "--language",
        "--lang",
        choices=SUPPORTED_LANGUAGES,
        default="en",
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
        "--alert-jsonl",
        metavar="FILE",
        help=(
            "append structured local JSONL alerts for a separate bridge; "
            "does not send in-game messages"
        ),
    )
    watch.add_argument(
        "--alert-pawn-file",
        metavar="FILE",
        help=(
            "append records for integrations/pawn/amxtriage_bridge.pwn; "
            "use the server scriptfiles path and load the filterscript separately"
        ),
    )
    watch.add_argument(
        "--alert-prefix",
        default=DEFAULT_ALERT_PREFIX,
        metavar="TEXT",
        help="prefix for alert summaries (requires --alert-jsonl or --alert-pawn-file)",
    )
    watch.add_argument(
        "--alert-message-template",
        default=DEFAULT_ALERT_MESSAGE_TEMPLATE,
        metavar="TEMPLATE",
        help=(
            "customize in-game message body with {severity}, {kind}, {message}, {code}, "
            "{signature}, {count}; source file and line are protected; requires --alert-pawn-file"
        ),
    )
    watch.add_argument(
        "--alert-cooldown",
        type=_alert_cooldown,
        default=300.0,
        metavar="SECONDS",
        help="suppress repeat alerts for the same diagnostic during this cooldown (default 300)",
    )
    watch.add_argument(
        "--alert-max-per-minute",
        type=_bounded_int(1, 300),
        default=60,
        metavar="COUNT",
        help="maximum number of alerts written per minute (default 60; max 300)",
    )
    watch.add_argument(
        "--alert-template",
        default=DEFAULT_ALERT_TEMPLATE,
        metavar="TEMPLATE",
        help=(
            "single-line JSONL alert template using safe fields such as {prefix}, {severity}, "
            "{file}, {line}, {message}; requires --alert-jsonl"
        ),
    )
    watch.add_argument(
        "--poll-interval",
        type=_poll_interval,
        default=DEFAULT_POLL_INTERVAL,
        metavar="SECONDS",
        help=f"seconds between checks for new lines (default {DEFAULT_POLL_INTERVAL})",
    )
    watch.add_argument(
        "--metrics-jsonl",
        metavar="FILE",
        help="append opt-in Linux host/process metrics and local alert-processing timings to FILE",
    )
    watch.add_argument(
        "--metrics-interval",
        type=_metrics_interval,
        default=DEFAULT_METRICS_INTERVAL_SECONDS,
        metavar="SECONDS",
        help=(
            "metrics sampling interval from 1 to 3600 seconds "
            "(default 5; requires --metrics-jsonl)"
        ),
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

    diagnose = commands.add_parser(
        "diagnose",
        aliases=["compiler"],
        help="analyze saved compiler/linter output without executing tools",
        description=(
            "Parse common compiler output formats from Pawn, Python, JavaScript/TypeScript, "
            "C/C++, Java, C#, Go and Rust. The command never launches a compiler."
        ),
    )
    _add_language_argument(diagnose)
    diagnose.add_argument(
        "logs", nargs="+", metavar="LOG", help="saved compiler output file(s); use '-' for stdin"
    )
    diagnose.add_argument(
        "--source-language",
        choices=COMPILER_LANGUAGES,
        default="auto",
        help="programming language/tool output format (default: auto)",
    )
    diagnose.add_argument("--format", choices=FORMATS, default="text", help="report format")
    diagnose.add_argument("-o", "--output", metavar="FILE", help="write the report to FILE")
    diagnose.add_argument(
        "--max-input-bytes",
        type=_size,
        default=0,
        metavar="SIZE",
        help="stop if an input exceeds SIZE after decompression (0 means no limit)",
    )

    patch_preview = commands.add_parser(
        "patch-preview",
        aliases=["fix-preview"],
        help="preview a conservative source patch from supported Pawn compiler output",
        description=(
            "Generate a unified diff for a narrow, high-confidence Pawn fix rule. This command "
            "never modifies source files or runs a compiler; uncertain cases are refused."
        ),
    )
    _add_language_argument(patch_preview)
    patch_preview.add_argument(
        "logs",
        nargs="+",
        metavar="COMPILER_LOG",
        help="saved Pawn compiler output file(s); use '-' for stdin",
    )
    patch_preview.add_argument(
        "--source-dir",
        required=True,
        metavar="DIR",
        help="root containing the Pawn source files; logged paths are used only for safe matching",
    )
    patch_preview.add_argument(
        "--format",
        choices=("text", "unified", "json"),
        default="text",
        help="text explanation, patch-only unified diff, or JSON result",
    )
    patch_preview.add_argument("-o", "--output", metavar="FILE", help="write preview/diff to FILE")
    patch_preview.add_argument(
        "--max-input-bytes",
        type=_size,
        default=0,
        metavar="SIZE",
        help="stop if a compiler log exceeds SIZE bytes after decompression (0 means no limit)",
    )

    patch_apply = commands.add_parser(
        "patch-apply",
        aliases=["fix-apply"],
        help="apply a reviewed Pawn patch with bounded compiler/test validation and rollback",
        description=(
            "Apply only the narrow patch produced by patch-preview using both reviewed SHA-256 "
            "hashes. A trusted local Pawn compiler and either --test-executable with optional "
            "--test-arg values or explicit --compile-only are required. Commands run without a "
            "shell and have time/output limits. Failed validation rolls back only while the target "
            "still matches the applied patch; external edits are preserved. Passing compilation "
            "and tests does not prove gameplay correctness."
        ),
    )
    _add_language_argument(patch_apply)
    patch_apply.add_argument(
        "logs", nargs="+", metavar="COMPILER_LOG", help="saved Pawn compiler output file(s)"
    )
    patch_apply.add_argument(
        "--source-dir",
        required=True,
        metavar="DIR",
        help="root containing Pawn source files; logged paths are used only for safe matching",
    )
    patch_apply.add_argument(
        "--compiler", required=True, metavar="PAWNCC", help="trusted local Pawn compiler executable"
    )
    test_validation = patch_apply.add_mutually_exclusive_group(required=True)
    test_validation.add_argument(
        "--test-executable",
        metavar="COMMAND",
        help="trusted local test/lint executable; invoked as argv without a shell",
    )
    test_validation.add_argument(
        "--compile-only",
        action="store_true",
        help="explicitly skip project tests (compiler success alone does not prove correctness)",
    )
    patch_apply.add_argument(
        "--test-arg",
        action="append",
        default=[],
        metavar="ARG",
        help="one literal argument passed to --test-executable; repeat as needed",
    )
    patch_apply.add_argument(
        "--include-dir",
        action="append",
        default=[],
        metavar="DIR",
        help="include directory for compiler validation; can be repeated",
    )
    patch_apply.add_argument(
        "--confirm-patch-sha256",
        required=True,
        type=_sha256_digest,
        metavar="SHA256",
        help="patch hash copied from a previously reviewed patch-preview",
    )
    patch_apply.add_argument(
        "--confirm-source-sha256",
        required=True,
        type=_sha256_digest,
        metavar="SHA256",
        help="source hash copied from the same reviewed patch-preview",
    )
    patch_apply.add_argument(
        "--timeout",
        type=_bounded_int(1, 120),
        default=30,
        metavar="SECONDS",
        help="compiler timeout from 1 to 120 seconds (default 30)",
    )
    patch_apply.add_argument(
        "--max-input-bytes",
        type=_size,
        default=0,
        metavar="SIZE",
        help="stop if a compiler log exceeds SIZE bytes after decompression (0 means no limit)",
    )

    explain = commands.add_parser(
        "explain",
        help="explain an AMX runtime error code (no code lists all known codes)",
    )
    _add_language_argument(explain)
    explain.add_argument("code", nargs="?", type=_bounded_int(0), metavar="CODE")

    catalog = commands.add_parser(
        "catalog",
        aliases=["plugins"],
        help="list plugins/components with upstream compatibility evidence",
        description=(
            "List the bundled offline compatibility snapshot. No network calls, downloads, or "
            "binary execution are performed. Documented does not mean runtime-tested."
        ),
    )
    _add_language_argument(catalog)
    catalog.add_argument(
        "--server",
        choices=("all", "open.mp", "sa-mp"),
        default="all",
        help="filter the exact target server (default: all)",
    )
    catalog.add_argument("--status", choices=STATUSES, help="filter by evidence status")
    catalog.add_argument(
        "--server-version",
        metavar="VERSION",
        help="filter an exact documented server version (no range matching)",
    )
    catalog.add_argument(
        "--os",
        "--platform",
        dest="platform",
        metavar="OS",
        help="filter an exact documented operating system/platform",
    )
    catalog.add_argument(
        "--arch",
        "--architecture",
        dest="architecture",
        metavar="ARCH",
        help="filter an exact documented CPU architecture",
    )
    catalog.add_argument(
        "--kind",
        choices=KINDS,
        help="filter by catalog kind: plugin, component, include or dependency",
    )
    catalog.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    catalog.add_argument("-o", "--output", metavar="FILE", help="write the catalog report to FILE")
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
    _write_output(
        render_report(report, args.format, show_args=args.show_args, language=args.language),
        args.output,
    )
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
    alert_sinks: Sequence[JsonlAlertSink | PawnBridgeAlertSink] = (),
    alert_throttle: AlertThrottle | None = None,
    metrics_sampler: MetricsSampler | None = None,
) -> None:
    added = aggregator.add(event, label)
    group = added.group
    if group is None:
        return
    if baseline is not None and group.signature_id in baseline:
        return
    if alert_sinks and (alert_throttle is None or alert_throttle.allow(group)):
        alert_started = time.perf_counter()
        for alert_sink in alert_sinks:
            if not alert_sink.emit(group) and not alert_sink.warning_emitted:
                detail = alert_sink.failure_reason or "write failed"
                print(
                    f"warning: local alert export disabled: {detail}",
                    file=sys.stderr,
                    flush=True,
                )
                alert_sink.warning_emitted = True
        if metrics_sampler is not None:
            # This measures local export handling, not the Pawn bridge's chat delivery.
            metrics_sampler.record_alert_processing((time.perf_counter() - alert_started) * 1000.0)
    if not added.created:
        return
    snippet = None
    if source_index is not None and args.context > 0:
        snippet = snippet_for(group, source_index, args.context)
    lines = render_group_text(
        group, show_args=args.show_args, snippet=snippet, new=True, language=args.language
    )
    print("\n".join(lines) + "\n", flush=True)


def _run_watch(args: argparse.Namespace) -> int:
    baseline = load_baseline(args.baseline) if args.baseline else None
    source_index = SourceIndex(args.source_dir) if args.source_dir else None
    if args.alert_template != DEFAULT_ALERT_TEMPLATE and not args.alert_jsonl:
        raise InputError("--alert-template requires --alert-jsonl")
    if args.alert_message_template != DEFAULT_ALERT_MESSAGE_TEMPLATE and not args.alert_pawn_file:
        raise InputError("--alert-message-template requires --alert-pawn-file")
    alert_sinks: list[JsonlAlertSink | PawnBridgeAlertSink] = []
    if args.alert_jsonl:
        alert_sinks.append(
            JsonlAlertSink(
                args.alert_jsonl,
                prefix=args.alert_prefix,
                template=args.alert_template,
            )
        )
    if args.alert_pawn_file:
        alert_sinks.append(
            PawnBridgeAlertSink(
                args.alert_pawn_file,
                prefix=args.alert_prefix,
                message_template=args.alert_message_template,
            )
        )
    alert_throttle = (
        AlertThrottle(
            cooldown_seconds=args.alert_cooldown,
            max_per_minute=args.alert_max_per_minute,
        )
        if alert_sinks
        else None
    )
    metrics_sampler: MetricsSampler | None = None
    metrics_sink: JsonlMetricsSink | None = None
    if args.metrics_jsonl:
        if not metrics_supported():
            raise InputError(
                "--metrics-jsonl is currently supported on Linux only; no metrics were collected"
            )
        metrics_path = Path(args.metrics_jsonl).expanduser().resolve()
        compared_paths = [Path(args.log).expanduser().resolve()]
        compared_paths.extend(
            Path(path).expanduser().resolve()
            for path in (args.alert_jsonl, args.alert_pawn_file)
            if path
        )
        if metrics_path in compared_paths:
            raise InputError(
                "metrics output must be a separate file from the log and alert outputs"
            )
        metrics_sampler = MetricsSampler(args.metrics_interval)
        metrics_sink = JsonlMetricsSink(args.metrics_jsonl)
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
                _announce_new_problem(
                    event,
                    aggregator,
                    label,
                    baseline,
                    source_index,
                    args,
                    alert_sinks,
                    alert_throttle,
                    metrics_sampler,
                )
            if (
                metrics_sampler is not None
                and metrics_sink is not None
                and metrics_sampler.due()
                and not metrics_sink.emit(metrics_sampler.sample())
                and not metrics_sink.warning_emitted
            ):
                detail = metrics_sink.failure_reason or "write failed"
                print(
                    f"warning: metrics export disabled: {detail}",
                    file=sys.stderr,
                    flush=True,
                )
                metrics_sink.warning_emitted = True
    except KeyboardInterrupt:
        pass
    finally:
        restore_signal()
        follower.close()
    for event in parser.finish():
        _announce_new_problem(
            event,
            aggregator,
            label,
            baseline,
            source_index,
            args,
            alert_sinks,
            alert_throttle,
            metrics_sampler,
        )
    if (
        metrics_sampler is not None
        and metrics_sink is not None
        and (not metrics_sampler.has_sampled or metrics_sampler.has_pending_alerts)
        and not metrics_sink.disabled
        and not metrics_sink.emit(metrics_sampler.sample())
        and not metrics_sink.warning_emitted
    ):
        detail = metrics_sink.failure_reason or "write failed"
        print(
            f"warning: metrics export disabled: {detail}",
            file=sys.stderr,
            flush=True,
        )
        metrics_sink.warning_emitted = True
    if alert_throttle is not None and alert_throttle.suppressed_count:
        print(
            "warning: suppressed "
            f"{alert_throttle.suppressed_count} alert(s) by cooldown/rate limit",
            file=sys.stderr,
            flush=True,
        )
    result = AnalysisResult([label], parser.line_number, follower.truncated_lines, aggregator)
    report = build_report(
        result,
        top=WATCH_SUMMARY_TOP,
        baseline=baseline,
        source_index=source_index,
        context_radius=0,
    )
    summary = render_report(report, "text", show_args=args.show_args, language=args.language)
    _write_output(tr(args.language, "watch_summary") + "\n" + summary, None)
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


def _run_diagnose(args: argparse.Namespace) -> int:
    report = analyze_compiler_outputs(
        expand_paths(args.logs),
        source_language=args.source_language,
        max_input_bytes=args.max_input_bytes or None,
    )
    _write_output(render_compiler_report(report, args.format, language=args.language), args.output)
    return EXIT_OK


def _run_patch_preview(args: argparse.Namespace) -> int:
    log_paths = expand_paths(args.logs)
    if args.format == "unified" and len(log_paths) > 1:
        raise InputError("patch-preview unified output accepts one compiler log at a time")
    source_index = SourceIndex(args.source_dir)
    report = analyze_compiler_outputs(
        log_paths,
        source_language="pawn",
        max_input_bytes=args.max_input_bytes or None,
    )
    preview = build_patch_preview(report.diagnostics, source_index)
    rendered = render_patch_preview(preview, args.format)
    if preview.status != "ready" and args.format == "unified":
        print(preview.message, file=sys.stderr, flush=True)
        return EXIT_NO_PATCH
    _write_output(rendered, args.output)
    return EXIT_OK if preview.status == "ready" else EXIT_NO_PATCH


def _run_patch_apply(args: argparse.Namespace) -> int:
    if args.test_arg and not args.test_executable:
        raise InputError("--test-arg requires --test-executable")
    log_paths = expand_paths(args.logs)
    source_index = SourceIndex(args.source_dir)
    report = analyze_compiler_outputs(
        log_paths,
        source_language="pawn",
        max_input_bytes=args.max_input_bytes or None,
    )
    preview = build_patch_preview(report.diagnostics, source_index)
    _write_output(render_patch_preview(preview, "text"), None)
    if preview.status != "ready":
        return EXIT_NO_PATCH
    result = apply_patch_preview(
        preview,
        source_index,
        expected_patch_sha256=args.confirm_patch_sha256,
        expected_source_sha256=args.confirm_source_sha256,
        compiler=args.compiler,
        include_dirs=args.include_dir,
        timeout_seconds=args.timeout,
        test_command=([args.test_executable, *args.test_arg] if args.test_executable else None),
        compile_only=args.compile_only,
    )
    print(f"Apply status: {result.status}")
    print(sanitize(result.message, MESSAGE_LIMIT))
    if result.backup_file:
        print(f"Backup: {sanitize(result.backup_file, MESSAGE_LIMIT)}")
    if result.compiler_exit_code is not None:
        print(f"Compiler exit code: {result.compiler_exit_code}")
    if result.compiler_output:
        print("Compiler output:")
        print(sanitize(result.compiler_output, MESSAGE_LIMIT * 4))
    if result.test_exit_code is not None:
        print(f"Test command exit code: {result.test_exit_code}")
    if result.test_output:
        print("Test command output:")
        print(sanitize(result.test_output, MESSAGE_LIMIT * 4))
    return EXIT_OK if result.status == "applied" else EXIT_ERROR


def _run_catalog(args: argparse.Namespace) -> int:
    snapshot = load_catalog()
    entries = filter_catalog_entries(
        snapshot.entries,
        server=args.server,
        status=args.status,
        server_version=args.server_version,
        platform=args.platform,
        architecture=args.architecture,
        kind=args.kind,
    )
    report = render_catalog_report(
        snapshot,
        entries,
        output_format=args.format,
        server=args.server,
        status=args.status,
        server_version=args.server_version,
        platform=args.platform,
        architecture=args.architecture,
        kind=args.kind,
        language=args.language,
    )
    _write_output(report, args.output)
    return EXIT_OK


def _run_explain(args: argparse.Namespace) -> int:
    if args.code is None:
        _write_output(render_error_list(args.language), None)
        return EXIT_OK
    error = lookup(args.code)
    if error is None:
        raise AmxTriageError(tr(args.language, "unknown_code").format(code=args.code))
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
    if args.command == "watch":
        if args.alert_template != DEFAULT_ALERT_TEMPLATE and not args.alert_jsonl:
            parser.error("--alert-template requires --alert-jsonl")
        if (
            args.alert_message_template != DEFAULT_ALERT_MESSAGE_TEMPLATE
            and not args.alert_pawn_file
        ):
            parser.error("--alert-message-template requires --alert-pawn-file")
        if (
            args.metrics_interval != DEFAULT_METRICS_INTERVAL_SECONDS
            and not args.metrics_jsonl
        ):
            parser.error("--metrics-interval requires --metrics-jsonl")
    try:
        if args.command == "analyze":
            return _run_analyze(args)
        if args.command == "watch":
            return _run_watch(args)
        if args.command in ("recommend", "suggest"):
            return _run_recommend(args)
        if args.command in ("diagnose", "compiler"):
            return _run_diagnose(args)
        if args.command in ("patch-preview", "fix-preview"):
            return _run_patch_preview(args)
        if args.command in ("patch-apply", "fix-apply"):
            return _run_patch_apply(args)
        if args.command in ("catalog", "plugins"):
            return _run_catalog(args)
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
