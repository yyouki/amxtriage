# HANDOFF

For the next developer or the next Claude session. Written at the end of the recovery session
of 2026-10-04 (sandbox clock). Read sections 1 and 2 first. Everything stated as verified was
read, run or measured in that session; what could not be verified is marked as such.

## 1. State in one paragraph

`amxtriage` is a working, stdlib-only Python 3.10+ command line tool that triages SA-MP and
open.mp server logs written by the crashdetect plugin (`analyze`, `watch`, `explain`). The
repository is the authoritative state: the working tree is clean at the commit that contains
this file, and the commit list in section 10 explains every change since the original baseline
`4c01dec`. All checks pass (section 6). Every file in the tree has been reviewed. The origin of
ten of them is still unknown, and section 5 records how they were checked and adopted.

## 2. Verify the state before trusting this file

```bash
git status --short                      # expect no output
git log --oneline | head -20            # compare with section 10
python -m venv .venv && . .venv/bin/activate
python -m pip install -e ".[dev]"
pytest -o addopts="" -q                 # 646 passed at the time of writing
ruff check . && ruff format --check .   # both clean
mypy                                    # no issues in 34 source files
python scripts/mutation_check.py --check   # the catalogue still matches the source
```

A passing test count is not proof that the tests are good. The proof used here is the mutation
check (section 6): break the code on purpose and see that tests fail.

## 3. Architecture

```text
file | .gz | stdin
  -> reader.iter_lines      1 MiB chunks, lines cut at 8192 bytes, binary check, gzip
  -> parser.LogParser       line -> Event; merges crashdetect block + Script[...] line
  -> aggregate.Aggregator   signature -> Group, with caps on groups, frames, line numbers
  -> analysis.build_report  filters, baseline, source snippets -> Report
  -> render.render_report   text | markdown | json

watch: follow.LogFollower yields lines (and None when idle) into the same parser and
aggregator and announces each new group once. cli.py wires everything and owns exit codes.
```

| Module | Responsibility |
|---|---|
| `reader.py` | `LineSplitter` (chunk safe, BOM, partial lines), `open_log`, `iter_lines`, `check_text_like` |
| `parser.py` | Regex based, all repetitions bounded. `LogParser.feed/flush`, frame and detail parsing |
| `aggregate.py` | `canonical_signature`, `signature_id`, `Aggregator`, `Group`, caps |
| `analysis.py` | `analyze_logs` (one parser per file), `build_report`, notes |
| `render.py` | Three formats, argument hiding, sanitising of every log-derived string |
| `source.py` | `SourceIndex`: index of real files, lookup by name, symlink checks, snippets |
| `baseline.py` | Atomic save, bounded and validated load (ids only are used) |
| `follow.py` | `LogFollower`: rotation, truncation, partial lines, injectable sleep and stop hooks |
| `textutil.py` | `sanitize`, `inline_code`, `basename` |
| `amxerrors.py` | Error code names and hints (names copied from crashdetect) |
| `cli.py` | argparse, `analyze`, `watch`, `explain`, exit codes 0, 1, 2, 130 |

Limits (constants in the modules): line 8192 bytes, chunk 1 MiB, groups 5000, AMX frames 48
and native frames 16 per event, line numbers 64 per group, baseline 10 MiB, source file 8 MiB,
`MESSAGE_LIMIT` 1000 characters for text echoed in terminal messages.

## 4. Design decisions that are not obvious from the code

Keep these unless a test or a real log shows they are wrong.

1. **A problem is identified by its error code, never by message text.** crashdetect prints
   code 19 as "File or function is not found", the server prints "...is not present".
   Signature string: `v1|kind|code|function|file basename|script|extra`. `extra` is the first
   native frame for crashes without AMX frames, or the sorted native names for codes 10 and 19.
2. **crashdetect's block and the server's `Script[...]` line are one event** when the code is
   the same and at most two unrelated lines lie between them (`QUIET_LINE_TOLERANCE`).
3. **Function arguments are hidden by default.** crashdetect logs string arguments verbatim;
   a login dialog `inputtext` is a password. `--show-args` is opt-in, and arguments are never
   written to a baseline or to JSON without the flag (also in `watch`, tested).
4. **Paths from a log are lookup keys, never filesystem paths.** `SourceIndex` lists the real
   `--source-dir` and the logged path only picks among the listed entries. Two layers protect
   against escapes: symlinked directories are not followed while indexing, and every read
   resolves the path again and requires it to stay under the root.
5. **All log-derived text goes through `sanitize()`**, in text, Markdown and JSON values, and
   so do file names echoed in stderr messages. JSON needs it even though `json.dumps` escapes
   control characters, because a consumer that decodes the JSON and prints a value would
   otherwise get the raw characters. The tests therefore decode the JSON before checking.
6. **Memory is bounded** by the limits above. Time is not bounded for decompressed size.
7. **Interrupt signals are parsed and ignored.** They are normal stops, counted in the notes.
8. **Only lines that start with the expected text count.** The match is anchored after the
   timestamp and up to three `[tag]` prefixes, so a player cannot forge an error by chatting it.
9. **`--save-baseline` stores every problem of the run**, whatever `--top`, `--min-count` or
   `--kind` show. Otherwise a filtered run would make old problems look new later.
10. **The signature scheme is locked** by a test (`test_signature_values_are_locked_for_baseline_compatibility`).
11. **In `watch`, the follower yields `None` when idle** so a block that is still open can be
    flushed. That is also the reason a very slow writer could split a block (section 8).
12. **Standard library only.** Dev tools are in the `dev` extra. Do not add a runtime dependency
    without a strong reason.

## 5. Provenance and recovery record

On 2026-10-02 the previous session stopped because files appeared that it had not written
(see its checkpoint, kept outside the repository, section 11). This session did the following.

**Authoritative baseline.** Commit `4c01dec` plus the `textutil.py` fix of the previous session.
The 37 hashes in `SESSION_MANIFEST.txt` all matched the snapshot, so the snapshot was
faithful. That says nothing about whether the unknown files were good, so they were reviewed.

**The ten files of unknown provenance** (`tests/test_analysis.py`, `test_baseline.py`,
`test_cli.py`, `test_follow.py`, `test_fuzz.py`, `test_render.py`, `test_security.py`,
`test_source.py`, `test_watch.py`, `scripts/make_synthetic_log.py`) were read in full and
scanned for network access, dynamic code, `shell=True`, destructive file operations and paths
outside `tmp_path`. Nothing harmful was found: hostile paths such as `/etc/passwd` appear only
as data, subprocesses use argument lists and timeouts. Their assertions match the design
decisions. Each of the nine test files fails at least one deliberately broken variant of the
code. They were committed byte for byte as found (hashes equal to the manifest) in `f057727`;
all later changes to them are separate commits. Who wrote them and why was **not determined**.
The hypothesis of the previous session (a parallel session working from the same plan) fits
but is unproven.

**The three files "reformatted by someone else"** (`test_aggregate.py`, `test_parser.py`,
`test_textutil.py`) were read in full. Content and test counts (14, 62, 29) match the checkpoint.

**`pyproject.toml`.** The unexplained change added `S105` and `S311` to the ruff ignores for
`tests/**`. Linting without it gives exactly six findings: `SECRET = "hunter2-secret"` in
`test_render.py` and `test_security.py` (a fake password to prove it never leaks, S105) and four
uses of the seeded `random.Random` in `test_fuzz.py` (S311). Justified, kept, committed alone.

**`textutil.py`.** Kept. Against the HEAD version, four tests fail (limits 0 to 3 return `...`).

**Corrections to the checkpoint.**

- Its mypy fix, `module = ["test_*", ...]`, does not work: mypy rejects the pattern. The modules
  are now listed by name (`[[tool.mypy.overrides]]`). A new test file must be added to that
  list, otherwise mypy fails.
- `.coverage` was not in the snapshot, so there was nothing to remove. It is in `.gitignore`.
- The file that `ruff format` wanted to change was `scripts/make_synthetic_log.py`. Its output is
  byte identical before and after the fix.

**Format facts, re-checked from source** (crashdetect `a537639`, fork `efbe179`, open.mp
`b6de2f2`):

| Fact | Where |
|---|---|
| `Run time error %d: "%s"`, `Server crashed while executing %s`, `... due to an unknown error`, `Server received interrupt signal [while executing %s]`, `AMX backtrace:`, `Native backtrace:`, `Registers:`, `Long callback execution detected (hang or performance issue)` | `src/crashdetect.cpp` (lines 312, 315, 331, 334, 356, 436, 499, 584, 642) |
| Detail lines start with one space after the `[debug]` prefix (two spaces in the log): array index, stack and heap pointers, unknown opcode, native names for codes 10 and 19 | `src/crashdetect.cpp` (around lines 360 to 420) |
| Frame layout `#N <8 hex> in [public ]name (args) at file:line`, `<unknown file>` | `src/amxstacktrace.cpp` |
| `variable arguments`, `<Foo:on, undefined>`, `native CallLocalFunction () from ...` | `tests/bad_frame.pwn`, `stacklow.pwn`, `states.pwn` |
| Old wording `Accessing element at index N past array upper bound M` | `tests/bad_frame.pwn:2` only. The current `src/` no longer prints it. Kept for old plugin versions |
| open.mp prints script errors as `<code> <message>`, not `Run time error` | open.mp `Manager.cpp` (lines 442, 559) and `Script.cpp:91`. Not parsed |
| `Script[file.amx]: Run time error N: "msg"` | **Not found in any of the three repositories.** It comes from the closed-source SA-MP server. Unverified |

The one unverified assumption carries weight: the merge of the two lines and the
`QUIET_LINE_TOLERANCE` rule depend on it. Check it against a real `server_log.txt`.

**Anomalies during the recovery session:** none. A tripwire (hash and modification time of every
file, plus HEAD) was checked after every step. The only differences it ever reported were the
changes made on purpose.

## 6. Verification record

Environment: Linux sandbox, 1 CPU, 4 GB RAM. Python 3.12.3, and 3.10.22, 3.11.17, 3.13.16
installed with `uv python install`. ruff 0.16.10, mypy 2.4.0, pytest 9.1.1, pytest-cov 7.1.0,
build 1.6.1, hatchling 1.32.4.

**Tests: 646, all passing** on Python 3.10.22, 3.11.17, 3.12.3 and 3.13.16.

| Origin | Files (tests) | Total |
|---|---|---|
| Written by the earlier session before the anomaly | `test_textutil` 29, `test_reader` 25, `test_parser` 62, `test_aggregate` 14 | 130 |
| Unknown provenance, reviewed and adopted | `test_analysis` 19, `test_baseline` 21, `test_cli` 45, `test_follow` 18, `test_fuzz` 311, `test_render` 22, `test_security` 18, `test_source` 35, `test_watch` 8 | 497 |
| Added in the recovery session | `test_hardening` | 19 |

Changes this session to adopted files: two type fixes (`test_render.py`, `test_watch.py`) and one
test in `test_follow.py` that now uses the bounded `follow()` helper.

**Mutation check.** `scripts/mutation_check.py` applies one fault at a time to a copy of the
tree: 98 mutants. At first, 15 of the first 94 survived against the adopted tests. 14 were real
gaps (sanitising of the error message, script name, function and file and of JSON values after
decoding, hostile file names, the native frame cap, baseline id length, symlinked directories,
`--save-baseline` with filters, line numbers per file, argument hiding in `watch`). They are
covered by `test_hardening`. The last one, `V12`, is an equivalent mutant: detail lines are
limited by strict regexes, so `sanitize` cannot change them. Final state: **97 killed, 1
equivalent, 0 unexpected survivors.** Every adopted test file kills at least one mutant.

**Static checks:** `ruff check .` and `ruff format --check .` clean (36 files: 34 Python and 2 Markdown), `mypy` strict on
`src`, `scripts` and the tests with their relaxation: no issues in 34 source files.

**Coverage** (pytest-cov, line and branch, measured before the last two fixes): 94 %. The
numbers for `cli.py` (73 %) and `__main__.py` (0 %) are low only because `watch` and `python -m`
run in subprocesses that this measurement does not trace.

**Packaging.** `python -m build` produced the wheel and the sdist. The wheel holds only the 15
modules and `py.typed` plus metadata (`Requires-Python >=3.10`, entry point
`amxtriage = amxtriage.cli:main`). Installed from the wheel and from the sdist, each in a fresh
venv that contained only `amxtriage` and `pip`: `scripts/smoke_installed.py` reported 14 passes
and 0 failures each time. The test suite also ran from the extracted sdist: 645 passed.

**Not tested:** Windows, macOS, other Linux distributions, a real SA-MP or open.mp server.

## 7. Security review

Concrete mitigations, each with its test. This is not a claim that the tool is secure.

| Threat | Mitigation | Evidence |
|---|---|---|
| Log injection and forged lines from chat | Anchored matching, so only lines that start with the expected text count | `test_security`, mutants P4, P5, P6 |
| Terminal escapes, bidi and format characters | `sanitize()` on every log-derived string and on file names in messages | `test_render`, `test_security`, `test_hardening`, mutants T1, T2, V3 to V11, E1 to E3 |
| Password leakage through arguments | Hidden unless `--show-args`, also in watch mode and JSON | `test_security`, `test_hardening`, mutants V1, V2, C4, C12, C13 |
| Path traversal | Log paths are only lookup keys | `test_source`, `test_security`, mutants S1, S9 |
| Symlink escape | Not followed while indexing, checked again at read time | `test_source`, `test_hardening`, mutants S1, S2 |
| Huge input and unbounded memory | Chunked reading, line cap, group and frame caps, baseline and source size caps | `test_reader`, `test_security`, `test_hardening`, mutants R1, R10, A2, A3, P2, P14, P15, B2, B6 |
| Malformed gzip, binary input, partial lines | Clean errors, probe for NUL and UTF-16 BOM | `test_reader`, `test_cli`, `test_follow`, mutants R2, R3, R8 |
| Slow regular expressions | Every repetition is bounded; stress lines tested | `test_security` (time bound 5 s) |
| Shell and subprocess risks | None in `src/`, no network import | `test_security`, grep of `src/` |

Found and fixed in the recovery session:

1. File names were echoed unsanitised in error messages, in `saved baseline ...` and in the
   `watching ...` banner (raw ESC and BEL reached stderr). Fixed in `cli.py`.
2. The baseline size limit was bypassed by files without a size (`/dev/zero`, named pipes): with
   a 400 MB limit, `--baseline /dev/zero` ended in an unhandled `MemoryError`. Fixed in `baseline.py`.

Remaining limitations (not fixed, documented in the README):

- A `.gz` file has no cap on its decompressed size. Memory stays flat, but time does not. A
  10 KB archive with 5 million short lines took 2.1 s, so about 1 MB of compressed data with
  500 million short lines would take roughly 3.5 minutes (an extrapolation, not a measurement).
  Use `timeout` or `ulimit -t` for untrusted archives.
- A person who can inject newlines into logged text can forge whole lines.
- Someone with write access to `--source-dir` can swap a file between the check and the read.
- `--show-args` output can contain passwords.
- `sanitize()` is not defined for a negative limit (a programming error, never log-derived).

## 8. Known limitations

- Formats: the `Script[...]` line is unverified from source (section 5). open.mp's own error
  lines are not parsed. crashdetect lines through open.mp's legacy plugin layer are accepted
  by design (any leading tags up to three) but were never seen on a real open.mp server.
- The block and `Script[...]` merge needs them within two unrelated lines. In `watch`, an idle
  flush during a long pause can split them into two events.
- `watch` misses a file that is truncated and regrows past its old size between two polls, and
  does not follow a rotation into `.gz`. By reading the code (not tested): after a rotation the
  new file is not probed for binary content again.
- The binary probe covers only the first 4096 bytes.
- `examples/sample_server_log.txt` is synthetic, built from the verified formats.
- Python 3.10 to 3.13 on Linux only.

## 9. Performance (measured)

Method: `scripts/make_synthetic_log.py --lines 1000000 --seed 1` (55.9 MB); larger files by
concatenating it 4 and 16 times; peak memory from `os.wait4` rusage; bytecode cache enabled.
One 1-CPU VM, so absolute numbers will differ elsewhere.

| Case | Wall time | Peak memory |
|---|---|---|
| Start-up, `explain 4`, median of 15 | 81 ms (empty Python 21 ms) | n/a |
| 1M lines, text / JSON / Markdown / `.gz` / stdin | 1.6 to 1.7 s (about 600k lines/s) | 25 MB |
| 4M lines (224 MB) | 6.0 s | 24.6 MB |
| 16M lines (895 MB) | 24.3 s | 24.7 MB |
| 5,000 distinct problems | 0.25 s | 27 MB |
| 300,000 distinct problems | 8.4 s, 295,000 events reported as not grouped | 31.5 MB |
| 1M events in one problem, 1M distinct line numbers (265 MB) | 28.3 s | 24.4 MB |
| One 200 MB line | 0.18 s | 21 MB |
| 1M lines of tag spam (47 MB) | 3.9 s | 25 MB |
| 100,000 lines of 8 KB with an unclosed quote (767 MB) | 1.1 s | 24 MB |
| `.gz` of 1 MiB that expands to 1 GiB without a newline | 2.6 s | 23 MB |
| `.gz` of 10 KB with 5M short lines | 2.1 s | 29 MB |
| `watch`, delay between a write and the announcement, 24 samples | 24 to 989 ms (poll interval 1.0 s) | n/a |
| `watch`, idle for 10 s | 0.07 s CPU (the start-up cost) | 19 MB |
| `watch --from-start` on 1M lines | caught up in under 2 s, 1.6 s CPU | 25 MB |

Lines that hold errors cost more than other lines: about 35,000 events per second against
600,000 plain lines per second. Nothing here was optimised, and nothing needs it yet.

## 10. History of the repository

| Commit | Subject |
|---|---|
| `4c01dec` | Add core: streaming reader, crashdetect parser, aggregation, renderers, CLI (original baseline) |
| `2253c45` | fix(textutil): sanitize() never returns more than the requested limit |
| `3b0f817` | build(ruff): ignore S105 and S311 for tests |
| `e5c9bdb` | test: add fixtures, helpers and the parser, reader and aggregator tests |
| `f057727` | test: adopt reviewed tests of unrecorded provenance |
| `38a8e06` | build(mypy): match the real module names of the tests in the override |
| `bd3bd70` | style: type-correct two adopted tests and wrap long lines in the log generator |
| `f15a851` | test: close the gaps found by mutation testing |
| `b4d0839` | fix(cli): sanitize file names echoed in terminal messages |
| `0f7c4be` | test: make the compressed-file follower test fail instead of hang |
| `2ae600e` | test: add the mutation check used in the recovery review |
| `b6572fc` | test: add a smoke test for an installed amxtriage |
| `7ce6f16` | fix(baseline): enforce the size limit by reading, not by stat() |
| (next) | docs: add README and HANDOFF, declare Python 3.13 as tested |

## 11. Remaining work, in order of value

1. **Check the `Script[...]` line against a real SA-MP `server_log.txt`**, and the merge rule with
   it. This is the largest unverified assumption.
2. Check a real open.mp server: the tags in front of crashdetect lines, and whether its own
   `<code> <message>` lines are worth parsing. Get the exact format from a real log first.
3. Test on Windows (and macOS). SA-MP servers often run on Windows. `watch` uses `st_ino` and
   signals, and the mutation script is POSIX only.
4. Add continuous integration: pytest on 3.10 to 3.13, ruff, mypy, `python -m build` and
   `scripts/smoke_installed.py` on the built wheel. There is no CI configuration yet.
5. Decide whether to cap decompressed size or line count (for example `--max-bytes`). Today it
   is documented only.
6. Give `watch` a grace period before it flushes an open block, to avoid splitting a block from
   its `Script[...]` line.
7. Make `sanitize()` reject or clamp a negative limit.
8. Decide about publishing. There is no release process, tag or PyPI configuration.

Deliberately not done: new features, a redesign, new dependencies, publishing.

## 12. Migration and upgrade notes

- **Signature scheme `v1`.** If the signature string ever changes, change `SIGNATURE_VERSION` in
  the same commit. Old baselines would then match nothing, every problem would look new, and
  `--fail-on-new` would fail. Plan a migration or tell users to save a new baseline.
- **JSON schemas.** The report and the baseline both carry `schema_version` 1. Adding fields is
  safe. Renaming, removing or changing meaning needs a new version. `load_baseline` rejects
  other versions.
- **Sanitising rules.** Changing what `sanitize()` replaces changes every output. Golden tests
  in `test_textutil`, `test_render` and `test_hardening` will tell you.
- **Python support.** `requires-python >=3.10` and `[tool.mypy] python_version = "3.10"` must
  move together. The classifiers list 3.10 to 3.13.
- **New test files** go into the mypy override list in `pyproject.toml`.
- **Mutation catalogue.** `scripts/mutants.json` matches exact source text. Run
  `python scripts/mutation_check.py --check` after a refactor and update what it reports.
- `HANDOFF.md` is listed in the sdist `include` of `pyproject.toml`.

## 13. Build and test commands

```bash
python -m pip install -e ".[dev]"
pytest                                    # configured in pyproject (addopts -ra -q)
pytest --cov                              # set COVERAGE_FILE outside the repo to keep it clean
ruff check . && ruff format --check .
mypy
python -m build --outdir /tmp/dist        # keeps the repo free of build/ and dist/
python scripts/smoke_installed.py /path/to/clean/venv/bin/python
python scripts/mutation_check.py          # about 10 minutes; give ids to run a few
python scripts/make_synthetic_log.py big.log --lines 1000000 --seed 1
```

Other Python versions without root: `pip install uv`, then `uv python install 3.10 3.11 3.13`,
`uv venv --python 3.10 /tmp/v310`, `uv pip install --python /tmp/v310/bin/python pytest`, and
`/tmp/v310/bin/python -m pytest`.

## 14. Working agreements

- One session works on the directory at a time. If a file changes that you did not change,
  stop, record it, and do not repair it blindly.
- Keep a simple tripwire while you work: hash and modification time of every tracked file plus
  `git rev-parse HEAD`, compared after each step.
- Inspect before you change. Small commits, one concern each. Foreign material goes into its own
  commit, unmodified, before anyone edits it.
- Never report a verification that was not run. Say what was run, on what, with what result.
- Do not claim the tool is secure. Describe mitigations and their limits.
- No placeholders, no fake features, no decorative output.

## 15. The earlier session's artifacts

`SESSION_CHECKPOINT.md`, `SESSION_MANIFEST.txt` and the snapshot zip of 2026-10-02 are not part of
the repository. They are historical and superseded: the manifest hashes no longer match the
tree, by design, because files were committed, fixed and added. They were handed over unchanged
next to this repository for traceability.
