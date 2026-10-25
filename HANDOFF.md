# HANDOFF

For the next developer or the next Claude session. Written at the end of the Phase 6 session
(security hardening). Read sections 1, 2 and 11 first. Statements marked **verified** were run
or measured in that session. Statements marked **recorded** come from the checkpoint of an
earlier session and were not repeated. Anything not marked is design information.

## 1. State in one paragraph

`amxtriage` is a stdlib-only Python 3.10+ command line tool that triages SA-MP and open.mp
server logs written by the crashdetect plugin (`analyze`, `watch`, `explain`). The repository
is the authoritative state. Code and tests are final at commit `0cb2399`; the commit after it
only changes Markdown and text files (README, this file, the checkpoint and the manifest).
Phase 6 (security hardening) is done: five weaknesses were reproduced and fixed, several other
areas were assessed and left alone, and each decision is recorded in section 7. Phases 7 to 13
are not done (section 11). The tool is **not** declared production ready: it was tested on Linux
only, there is no CI, and the `Script[...]` line is still unverified against a real server.

## 2. Verify the state before trusting this file

```bash
git status --short                         # expect no output
git log --oneline | head -12               # compare with section 10
python -m venv .venv && . .venv/bin/activate
python -m pip install -e ".[dev]"
pytest                                     # 1763 passed, 1 skipped when run as root
ruff check . && ruff format --check .      # both clean
mypy                                       # no issues in 46 source files
python scripts/mutation_check.py --check   # 203 mutants, every specification matches
```

The one skipped test (`test_an_unreadable_baseline_is_a_clean_error`) needs a user that file
permissions apply to. Run it as a normal user to execute it. A passing test count is not proof
that the tests are good; the proof used here is the mutation check (section 6).

## 3. Architecture

```text
file | .gz | stdin
  -> reader.iter_lines      1 MiB chunks, lines cut at 8192 bytes, binary check, gzip
  -> parser.LogParser       line -> Event; merges crashdetect block + Script[...] line
  -> aggregate.Aggregator   signature -> Group, with caps on groups, frames, line numbers
  -> analysis.build_report  filters, baseline, source snippets -> Report
  -> render.render_report   text | markdown | json
  -> cli._write_output      stdout, or output.write_text_file for -o

watch: follow.LogFollower yields lines (and None when idle) into the same parser and
aggregator and announces each new group once. cli.py wires everything and owns exit codes.
```

| Module | Responsibility |
|---|---|
| `reader.py` | `LineSplitter` (chunk safe, BOM, partial lines), `open_log`, `iter_lines`, `check_text_like`, `--max-input-bytes` |
| `parser.py` | Regex based, all repetitions bounded. `LogParser.feed/flush`, frame and detail parsing. Stores at most `MAX_STORED_ARGS` characters of a frame's arguments |
| `model.py` | `Event`, `Frame`, `Group` and the shared constants `ARGS_DISPLAY_LIMIT` (400) and `MAX_STORED_ARGS` (401) |
| `aggregate.py` | `canonical_signature`, `signature_id`, `Aggregator`, `Group`, caps |
| `analysis.py` | `analyze_logs` (one parser per file), `build_report`, notes |
| `render.py` | Three formats, argument hiding, sanitising of every log-derived string |
| `source.py` | `SourceIndex`: index of real files, lookup by name. `_checked_path` resolves a path and records its device and inode; `_open_verified` opens it without following links and checks it again with `fstat` |
| `baseline.py` | Atomic save; bounded, strict load (ids only are used) |
| `output.py` | `write_text_file`: the writer behind `-o` (refuses symlinks and multiply linked files) |
| `follow.py` | `LogFollower`: rotation, truncation, partial lines, injectable sleep and stop hooks |
| `textutil.py` | `sanitize`, `inline_code`, `basename` |
| `amxerrors.py` | Error code names and hints (names copied from crashdetect) |
| `errors.py` | `AmxTriageError` and its subclasses (`BaselineError`, `SourceError`, `OutputError`, ...) |
| `cli.py` | argparse, `analyze`, `watch`, `explain`, exit codes 0, 1, 2, 130, the internal error boundary |

Limits (constants in the modules): line 8192 bytes, chunk 1 MiB, groups 5000, AMX frames 48
and native frames 16 per event, line numbers 64 per group, stored arguments 401 characters
(shown: 400), baseline 10 MiB and integers of at most 32 digits, source file 8 MiB, at most
50,000 indexed source files and 20,000 scanned directories, `MESSAGE_LIMIT` 1000 characters
for text echoed in terminal messages, 5 places in an internal error message.

## 4. Design decisions that are not obvious from the code

Keep these unless a test or a real log shows they are wrong.

1. **A problem is identified by its error code, never by message text.** crashdetect prints
   code 19 as "File or function is not found", the server prints "...is not present".
   Signature string: `v1|kind|code|function|file basename|script|extra`. `extra` is the first
   native frame for crashes without AMX frames, or the sorted native names for codes 10 and 19.
2. **crashdetect's block and the server's `Script[...]` line are one event** when the code is
   the same and at most two unrelated lines lie between them (`QUIET_LINE_TOLERANCE`). In
   `watch` a pending block waits two quiet polls before it is flushed.
3. **Function arguments are hidden by default.** crashdetect logs string arguments verbatim;
   a login dialog `inputtext` is a password. `--show-args` is opt-in, and arguments are never
   written to a baseline or to JSON without the flag (also in `watch`, tested).
4. **Paths from a log are lookup keys, never filesystem paths.** `SourceIndex` lists the real
   `--source-dir` and the logged path only picks among the listed entries. Symlinked
   directories are not followed while indexing. A lookup resolves the path and requires it to
   stay under the root; opening then starts at the root and goes component by component with
   `O_NOFOLLOW`, so replacing a file after the check cannot lead outside the root (decision 13).
5. **All log-derived text goes through `sanitize()`**, in text, Markdown and JSON values, and
   so do file names echoed in stderr messages. JSON needs it even though `json.dumps` escapes
   control characters, because a consumer that decodes the JSON and prints a value would
   otherwise get the raw characters. The tests therefore decode the JSON before checking.
6. **Memory is bounded** by the limits above. Time is bounded for decompressed size only with
   `--max-input-bytes`. "Bounded" is not "small": section 7 has the measured worst case.
7. **Interrupt signals are parsed and ignored.** They are normal stops, counted in the notes.
8. **Only lines that start with the expected text count.** The match is anchored after the
   timestamp and up to three `[tag]` prefixes, so a player cannot forge an error by chatting it.
9. **`--save-baseline` stores every problem of the run**, whatever `--top`, `--min-count` or
   `--kind` show. Otherwise a filtered run would make old problems look new later.
10. **The signature scheme is locked** by a test (`test_signature_values_are_locked_for_baseline_compatibility`).
11. **In `watch`, the follower yields `None` when idle** so a block that is still open can be
    flushed.
12. **Standard library only.** Dev tools are in the `dev` extra. Do not add a runtime dependency
    without a strong reason.
13. **Files whose name comes from untrusted text are opened without following links and
    verified after opening.** That is the source files (`source.py`). Files that the user names
    are different: the log and the baseline are opened normally, because named pipes and process
    substitution (`--baseline <(git show main:baseline.json)`) are legitimate there, so the
    baseline reader reads a pipe up to the size limit instead of refusing it. Output files are
    covered by decision 16.
14. **Status 1 means new problems and nothing else.** `main()` ends with a handler for any
    unexpected exception: status 2 and a short message with the exception type and the
    innermost places (file, line, function, no directory). The text of the exception is never
    printed, because it can hold data from the log. `KeyboardInterrupt` (130), a closed pipe
    (0) and `SystemExit` are not touched.
15. **A baseline is rejected, never repaired.** `json.loads` gets hooks (`parse_int` refuses
    numbers of more than 32 digits before `int()` runs, `parse_constant` refuses NaN and
    Infinity), so there is no broad `except ValueError`. `schema_version` must be exactly the
    integer 1 (`True` and `1.0` equal 1 in Python). One leading UTF-8 byte order mark is
    accepted (RFC 8259 allows readers to ignore it). Messages never repeat values from the file.
16. **`-o` and `--save-baseline` are deliberately different.** `--save-baseline` writes a
    temporary file and renames it, which replaces a link instead of following it. `-o` must
    also work for devices (`-o /dev/null`), which a rename would replace, so it opens with
    `O_NOFOLLOW`, refuses a regular file with several hard links before truncating anything,
    and truncates only regular files.
17. **Stored arguments are cut at `ARGS_DISPLAY_LIMIT + 1`.** The extra character is what lets
    `sanitize()` still add its ellipsis. Output is identical to storing everything (a test
    compares both for lengths 1 to 7000, in all formats, with and without `--show-args`).

## 5. Provenance and recovery record

**Sessions.** (1) The original session produced baseline `4c01dec`; it stopped on 2026-10-02
because files appeared that it had not written. (2) A recovery session (2026-10-04) reviewed
ten files of unknown origin and adopted them. (3) A session carried out Phases 0 to 5 (format
audit, parser fixes, watch grace period, `--max-input-bytes`) and stopped when six tracked source
files changed on disk without any action of its own. (4) The Phase 6 session, which wrote this
file.

**Recovery session (recorded).** The ten files of unknown provenance (`tests/test_analysis.py`,
`test_baseline.py`, `test_cli.py`, `test_follow.py`, `test_fuzz.py`, `test_render.py`,
`test_security.py`, `test_source.py`, `test_watch.py`, `scripts/make_synthetic_log.py`) were read
in full and scanned for network access, dynamic code, `shell=True`, destructive file operations
and paths outside `tmp_path`. Nothing harmful was found. They were committed byte for byte in
`f057727`. Who wrote them was **not determined**. `pyproject.toml` got `S105` and `S311` ignores
for tests (fake passwords and a seeded `random.Random`), and `textutil.sanitize()` was fixed so it
never returns more than the limit.

**Session 3 (recorded).** Its six commits are in section 10. It stopped because six files under
`src/amxtriage/` (`baseline.py`, `parser.py`, `cli.py`, `model.py`, `render.py`, `source.py`)
differed from HEAD in the original workspace, with no command of that session having written
them. It left the original workspace as found, took an archive of it and a patch
(`anomaly-evidence.zip`, 62 insertions and 13 deletions, never applied), and delivered a clean
snapshot of `21fa90f`. Who or what wrote the changes is **unknown**.

**Session 4, this one (verified).**

- The snapshot zip was listed before extraction: 446 entries, one top-level folder, no absolute
  or `..` paths, no symlinks, `testzip` clean. `.git/config` and the hooks folder were read
  before any `git` command: no hooks, no filters, no `fsmonitor`.
- HEAD was `21fa90fac2b326bd13dac5de8325458040fa2c98`, branch `main`, tree clean, `git fsck
  --full` clean, 20 commits. The 72 tracked files matched the manifest by SHA-256, the six
  commit ids of session 3 existed with the recorded subjects, and the six blob ids that the
  checkpoint names for HEAD matched.
- The recorded baseline was reproduced before any change: 1506 tests passed on Python 3.10.20,
  3.11.15, 3.12.3 and 3.13.13; ruff, ruff format and mypy strict were clean.
- A tripwire outside the repository (SHA-256, size, mode and mtime of every tracked file, the
  content hash of untracked files, HEAD and `git status`) was checked before and after every
  substantial operation, including every mutation run. **It reported no unexplained change.**
  Every difference it reported was one this session made on purpose.
- `anomaly-evidence.zip` was not among the files given to this session, so the foreign patch
  was never seen. Only the checkpoint's description of it was used, as a list of questions.
  Everything was reimplemented from the reproduced failures. Where the description says what
  the foreign patch did, the differences are: the baseline loader uses `json.loads` hooks and
  not `except ValueError`; the internal error message prints the exception type and places and
  not the text and a traceback; source files are opened component by component and not only
  with `O_NOFOLLOW` on the last component plus an inode comparison; `-o` and the explain,
  rendering and tree-size assessments are new.

**Format facts.** The evidence for every log format, with its level, is in
`docs/LOG_FORMATS.md`. One point carries weight: the `Script[file.amx]: Run time error N:
"msg"` line is printed by the closed-source SA-MP server and was **not found in any open-source
repository**. The merge of the two lines and `QUIET_LINE_TOLERANCE` depend on it. Check it
against a real `server_log.txt`. (Session 3 could not find the crashdetect commit ids that the
older handoff named; the `Y-Less` fork was used. open.mp revision `b6de2f2` matched.)

## 6. Verification record

Environment (verified): Linux sandbox, 1 CPU, about 4 GB RAM, running as root. Python 3.12.3,
and 3.10.20, 3.11.15 and 3.13.13 installed with `uv python install`. ruff 0.17.2, mypy 2.4.0,
pytest 9.1.1, pytest-cov 7.1.0, coverage 7.17.0, build 1.6.1, hatchling 1.32.4, twine 7.0.0.

**Tests: 1764 collected, 1763 passed and 1 skipped** on Python 3.10.20, 3.11.15, 3.12.3 and
3.13.13, on the final code. The same count passed from the extracted sdist (Python 3.12). The
skipped test passes when run as the unprivileged user `nobody`.

| File | Tests | File | Tests |
|---|---|---|---|
| `test_aggregate` | 14 | `test_internal_errors` | 13 |
| `test_analysis` | 19 | `test_output` | 24 |
| `test_argument_storage` | 34 | `test_parser` | 172 |
| `test_baseline` | 21 | `test_parser_model` | 500 |
| `test_baseline_hardening` | 77 | `test_reader` | 25 |
| `test_cli` | 45 | `test_render` | 22 |
| `test_explain_inputs` | 17 | `test_rendering_hostile` | 40 |
| `test_follow` | 35 | `test_security` | 18 |
| `test_format_fixtures` | 178 | `test_source` | 35 |
| `test_fuzz` | 311 | `test_source_race` | 53 |
| `test_hardening` | 19 | `test_textutil` | 29 |
| `test_input_limits` | 50 | `test_watch` / `test_watch_loop` | 8 / 5 |

Phase 6 added 258 tests (1506 before): baseline hardening 77, internal errors 13, source race 53,
argument storage 34, output 24, hostile rendering 40, explain 17. Every new test was written
before its fix and seen to fail on the old behaviour.

**Mutation check.** `scripts/mutation_check.py` applies one fault at a time to a copy of the
tree. The catalogue has 203 mutants (139 before Phase 6, 64 added). The full catalogue was run on the final
source (201 mutants on the tree at `984b155`, whose `src/` is identical to the final one, and
the two mutants added afterwards on the final tree): **202 killed, 1 survivor.** The survivor is
`V12`, declared equivalent: detail lines are limited by strict regexes, so `sanitize` cannot
change them. `R15` is killed only by a timeout. `--check` confirms that every specification
still matches the source.

**Static checks (verified):** `ruff check .` and `ruff format --check .` clean (49 files),
`mypy` strict clean (46 source files).

**Coverage** (Python 3.12, line and branch): 98 %, 1521 statements with 24 missed and 456
branches with 13 partial (before Phase 6: 1406 and 29, 428 and 14, also 98 %). `source.py` and
`output.py` are fully covered. Lowest: `__main__.py` 0 % (it runs in a subprocess), `cli.py` 94 %.

**Packaging (verified).** `python -m build` made the wheel and the sdist; `twine check` passed
for both. The wheel has 22 entries: the 16 modules (including the new `output.py`), `py.typed`
and the metadata. The sdist has `HANDOFF.md`, `README.md`, `src/`, `tests/`, `scripts/`,
`examples/`, and no `docs/`. Each installed into a clean venv (Python 3.12),
`scripts/smoke_installed.py` reported 14 passes and 0 failures.

**Compatibility with `21fa90f` (verified).** The old and the new code were run on the sample
log and on a synthetic log of 2,000,000 lines (117 MB), in text, Markdown and JSON, with and
without `--show-args` and `--source-dir`, and with `--fail-on-new --top 50`: **30 of 30 runs gave
the same exit status, stdout and stderr, byte for byte.** `--save-baseline` wrote identical files,
and each version read the other's baseline. The new code was not slower (3.25 to 3.37 s against
3.44 to 3.86 s for 2,000,000 lines, same VM).

**Not tested:** Windows, macOS, other Linux distributions, other file systems than the sandbox's
ext4-like one, a real SA-MP or open.mp server, any CI.

## 7. Security review (Phase 6)

### 7.1 What was investigated and what was found

Every area was reproduced or measured on the unchanged commit `21fa90f` before any code changed.

| Area | Result on `21fa90f` | Decision |
|---|---|---|
| Baseline: integer of more than 4,300 digits | `ValueError` from `int()`, traceback, **exit status 1** (the status of "new problems") | Fixed |
| Baseline: `schema_version` `true` and `1.0`; `NaN`, `-Infinity` | Accepted as a valid baseline | Fixed |
| Baseline: UTF-8 byte order mark | Rejected with a clear message | One BOM accepted |
| Baseline: 10 MiB of minimal entries (476,617) | 0.44 s, 158 MB peak | Bounded, unchanged |
| Baseline: directory, unreadable file, `/dev/zero` | Clean error, status 2 | Unchanged |
| Baseline: named pipe with no writer | Waits (by design, a test pins reading a pipe) | Unchanged |
| Source lookup: file swapped after the check | Symlink, hard link and symlinked directory leaked lines of a file outside the root; a named pipe blocked forever; a 300 MiB file used 623 MB | Fixed |
| Frame arguments | 1,924 MB at 5,000 problems (7.3 s); 1,917 MB for a log with every field at its limit (18 s) | Fixed |
| `-o` | Followed a symlink and truncated its target; wrote into a file with other names | Fixed |
| Any unexpected exception | Python's exit status 1 | Fixed |
| `explain` with odd arguments | Every case ends as a usage error (2) or an answer, no traceback | Tests only |
| 5,000-digit numbers in any numeric position of a log line | No exception (regexes bound the digits) | Unchanged |
| Hostile text and file names in text, Markdown, JSON | No finding in 40 seeds. The test fails when `sanitize` is weakened | Test only |
| 600,000 distinct problems | 31 MB flat, 18 s | Unchanged |
| One folder with 400,000 files | Index in 1.8 to 2.1 s, 80 MB peak in total | Unchanged, documented |
| 32,000 files with the same name | 16 to 20 ms per lookup | Unchanged, documented |

### 7.2 Fixes

| Commit | Change | New tests | Mutants |
|---|---|---|---|
| `5e285fe` | Baseline loader: hooks, strict version type, BOM, no echo of file values | 77 | B7 to B18, B1 retargeted |
| `674d5d2` | Internal error boundary in `main()` | 13 | C20 to C28 |
| `2853439` | Source files opened component by component with `O_NOFOLLOW`, `O_NONBLOCK`, checked with `fstat`, bounded reads | 45 | S12 to S32, S1, S5, S11 retargeted |
| `61002ee` | Arguments stored up to 401 characters | 34 | P38 to P42, V13, V14 |
| `ddde066` | `output.py`: `-o` refuses symlinks and multiply linked files | 24 | O1 to O12, C29 |
| `5fc8837`, `984b155` | Regression tests for rendering and for `explain` | 40, 17 | none needed |
| `0cb2399` | Tests for a file that vanishes or loops after indexing | 8 | S33, S34 |

Measured effect of the argument limit (same machine and method): 5,000 problems with 8,000
character arguments 1,924 MB to 178 MB; the log with every stored field at its limit 1,917 MB to
320 MB. The remaining 320 MB is the other stored fields (file 500, module 260, function 128
characters, 48 frames per problem). They are part of the JSON contract and of the signature,
so they were not cut.

### 7.3 Mitigations and their evidence

| Threat | Mitigation | Evidence |
|---|---|---|
| Log injection and forged lines from chat | Anchored matching | `test_security`, mutants P4, P5, P6 |
| Terminal escapes, bidi and format characters | `sanitize()` on every log-derived string and on file names in messages | `test_render`, `test_security`, `test_hardening`, `test_rendering_hostile`, mutants T1, T2, V3 to V11, E1 to E3 |
| Markdown injection | Untrusted text only inside code spans or fences | `test_rendering_hostile` |
| Password leakage through arguments | Hidden unless `--show-args` | `test_security`, `test_hardening`, mutants V1, V2, C4, C12, C13 |
| Path traversal | Log paths are only lookup keys | `test_source`, `test_security`, mutants S1, S9 |
| Source file swapped after the check | Anchored `O_NOFOLLOW` open, `fstat` identity and type check, bounded read | `test_source_race`, mutants S12 to S34 |
| Report written through a link | `output.write_text_file` | `test_output`, mutants O1 to O12, C29 |
| A bug mistaken for a finding | Internal error boundary, status 2 | `test_internal_errors`, mutants C20 to C28 |
| Malformed baseline | Hooks, strict validation, size limit | `test_baseline`, `test_baseline_hardening`, `test_hardening`, mutants B1 to B18 |
| Huge input and unbounded memory | Chunked reading, line cap, group, frame and argument caps, size caps, `--max-input-bytes` | `test_reader`, `test_input_limits`, `test_argument_storage`, `test_hardening`, mutants R, A, P, B |
| Malformed gzip, binary input, partial lines | Clean errors, probe for NUL and UTF-16 BOM | `test_reader`, `test_cli`, `test_follow` |
| Slow regular expressions | Every repetition is bounded; stress lines tested | `test_security`, `test_parser_model` |
| Shell and subprocess risks | None in `src/`, no network import | `test_security` |

### 7.4 Remaining risks and untested behaviour

- **Windows and macOS were not tested.** `O_NOFOLLOW` does not exist on Windows. There the source
  file is opened by path and only the `fstat` checks apply (type, size, device and inode where
  the file system reports an inode); a link that leads to the very same file is not detected.
  `-o` follows symlinks on Windows. The fallback code is exercised on Linux by tests that
  switch the flags off; those tests are skipped on Windows (the whole module is), so nothing
  runs the fallback on the platform it is meant for. Other POSIX systems (macOS, BSD) were not
  tested either; the code accepts `EMLINK` and `EFTYPE` for the refused symlink, from the
  documentation of those systems and not from a test.
- **Hard links.** A hard link to a file outside `--source-dir` cannot be told from a normal file.
- **`-o`** checks only the last path component. A symlink in a folder name is followed.
- **File systems without stable inode numbers** (inode 0 is accepted without a comparison; an
  inode that changes between `stat` and `fstat` makes the snippet disappear).
- **Memory** is bounded but not small: 320 MB for the worst log found, 158 MB while reading a
  10 MiB baseline.
- **Tree size.** No cap on entries in a single `--source-dir` folder; `find()` compares all files
  of one name.
- **Time** for `.gz` input is bounded only with `--max-input-bytes`.
- **Internal error messages** print the class name of the exception. The name is sanitised, and
  log data cannot create a class, so this is not a way in.
- The assessment covers the code paths named here. It is not a guarantee, and a passing test
  suite is not a statement that the project is production ready.

### 7.5 Decisions the owner may want to revisit

1. **A BOM is accepted** in a baseline. Rejecting it again is a one-line change (mutant B7 shows
   where) but would make baselines saved by some Windows editors fail.
2. **`-o /dev/stdout` is refused**, because it is a symlink. Allowing symlinks that lead to
   non-regular files would allow `link -> /dev/sda`, which is why it was not done.
3. **Internal errors use status 2**, not a new status, so the set 0, 1, 2, 130 is unchanged.
4. **The baseline size limit stayed at 10 MiB.** A legitimate baseline has at most 5,000 entries.
5. **Four things were assessed and left unchanged** with numbers (table 7.1): large baseline,
   large source folder, same-name candidates, many problems.

## 8. Known limitations

Recorded by session 3 (not repeated here) unless noted.

- `watch`: truncation is detected by size only; a file truncated and regrown past its old size
  within one poll is not noticed (pinned by a test).
- `watch`: a file rotated away twice within one poll loses the middle file (pinned by a test).
- `watch`: the file must exist when it starts, and it does not follow a rotation into `.gz`.
- `watch`: a block waits two quiet polls, so a problem can be announced up to about two poll
  intervals late.
- Parser: whether the server prints `Script[...]` for failures inside public callbacks is
  unknown; frames split by a newline in a string argument are dropped; `????????` addresses
  (crashdetect 4.10 and earlier) and the missing native names in `Error: Function not
  registered` lines are not parsed; open.mp's own error lines are not parsed; two non-empty
  code 19 blocks before one `Script[...]` stay two events.
- The binary probe covers only the first 4,096 bytes.
- `examples/sample_server_log.txt` is synthetic, built from the verified formats.
- Python 3.10 to 3.13 on Linux only.

## 9. Performance (measured)

Method: `scripts/make_synthetic_log.py --lines 1000000 --seed 1` (55.9 MB); peak memory from
`os.wait4` rusage. Rows marked **R** were recorded by an earlier session on another VM; rows
marked **V** were measured in the Phase 6 session on the sandbox described in section 6. Absolute
numbers differ between machines; compare rows of the same mark.

| Case | Wall time | Peak memory |
|---|---|---|
| R: 1M lines, text / JSON / Markdown / `.gz` / stdin | 1.6 to 1.7 s (about 600k lines/s) | 25 MB |
| R: 2M lines (117.3 MB) | 2.3 to 2.5 s | n/a |
| R: 16M lines (895 MB) | 24.3 s | 24.7 MB |
| R: 300,000 distinct problems | 8.4 s, 295,000 events reported as not grouped | 31.5 MB |
| R: 1M events in one problem, 1M distinct line numbers (265 MB) | 28.3 s | 24.4 MB |
| R: one 200 MB line | 0.18 s | 21 MB |
| R: `.gz` of 19.7 MB that expands to 2 GiB | 15.6 s with no limit, 2.06 s with `--max-input-bytes 256M`, 0.59 s with 64M | about 25 MB |
| R: `watch`, delay between a write and the announcement | 24 to 989 ms (poll 1.0 s) | n/a |
| V: 2M lines (117 MB), JSON, new code and `21fa90f` | 3.25 to 3.37 s and 3.44 to 3.86 s | n/a |
| V: 600,000 distinct problems | 18 s | 31 MB |
| V: 5,000 problems of 48 frames with 8,000-character arguments | 5.7 s (7.3 s before the argument limit) | 178 MB (1,924 MB before) |
| V: the same with every stored field at its limit | 7.6 s (18 s before) | 320 MB (1,917 MB before) |
| V: baseline of 10 MiB, 476,617 entries | about 0.5 s | 158 MB |
| V: one source folder with 400,000 files | 1.8 to 2.1 s | 80 MB |
| V: 32,000 source files with the same name | 16 to 20 ms per lookup | 18 MB |

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
| `e2e4f3c` | docs: add README and HANDOFF, declare Python 3.13 as tested |
| `0c12ab3` | fix(parser): close gaps found by the log format audit |
| `43e3823` | docs: record verified SA-MP and open.mp log formats |
| `3598e84` | test(parser): add a model-based grammar test and more pathological shapes |
| `8576f1b` | test(mutation): cover the parser rules added by the format audit |
| `ddc13a9` | fix(watch): give a pending block time to receive its Script line |
| `21fa90f` | feat(analyze): add --max-input-bytes to bound the work done per input |
| `5e285fe` | fix(baseline): reject oversized numbers and wrong types without a traceback |
| `674d5d2` | fix(cli): an unexpected exception must not exit with status 1 |
| `2853439` | fix(source): open source files without following links and check them after opening |
| `61002ee` | fix(parser): store at most 401 characters of each frame argument list |
| `ddde066` | fix(cli): do not write the report through a symbolic link or a hard link |
| `5fc8837` | test(render): add a seeded test for hostile names and text in every output |
| `984b155` | test(cli): pin how explain handles unusual error codes |
| `0cb2399` | test(source): cover a file that vanishes or loops after indexing |
| (next) | docs: update README, HANDOFF, checkpoint and manifest after Phase 6 |

## 11. Remaining work, in order of value

Phases 7 to 13 were not started. The plan below comes from the checkpoint of session 3 and was
completed with what Phase 6 learned. Phases 9 and 10 are not described in any file that the
Phase 6 session was given; take their definition from the original task statement.

1. **Phase 7, other platforms.** Known risks: the follower keeps the log open (Windows opens
   without share-delete, so the log may not be renameable or deletable while `watch` runs);
   `st_ino` may be zero on some Windows file systems, which would hide rotation; the signal
   tests and the smoke test use POSIX signals; `O_NOFOLLOW` does not exist on Windows (the
   anchored open in `source.py` and the symlink check in `output.py` fall back to weaker
   checks, section 7.4); non-UTF-8 logs (Windows code pages) turn non-ASCII characters into
   U+FFFD; README commands are shell specific; waiting on an event cannot be interrupted by
   Ctrl+C on Windows (believed, not tested). Also: `test_source_race.py`, `test_output.py` and
   `test_rendering_hostile.py` are skipped as a whole on Windows, so Windows needs its own tests
   of the fallback paths. macOS and BSD need a run of the new `O_NOFOLLOW` code.
2. **Phase 8, CI.** There is no `.github/` folder. A small workflow: Python 3.10 to 3.13 on Linux
   running ruff, the format check, mypy, pytest and the build; one Windows job and one macOS job
   on one Python version. The full mutation run takes about 35 minutes on one CPU, so keep it
   manual or scheduled. One shell command may be limited to 300 s: run mutants in chunks of
   about 24 ids.
3. **Phase 11, packaging.** The sdist contains `HANDOFF.md` but not `docs/`; decide whether either
   belongs there. The metadata says `Operating System :: OS Independent`, which is not backed by
   tests on Windows or macOS, and `Development Status :: 4 - Beta`; review both.
4. **Phase 12, README.** Rewrite from verified behaviour only, with five categories: supported,
   tested, partially tested, unknown, unsupported.
5. **Phase 13, release.** Phase 6 changed behaviour: a new option (`--max-input-bytes`, session 3),
   `-o` refusing symlinks and multiply linked files, a stricter baseline reader, different
   internal error behaviour. A minor version (`0.2.0`) fits better than `0.1.1`. Do not bump the
   version before the end.
6. **Open questions that carry weight:** check the `Script[...]` line and the merge rule against a
   real SA-MP `server_log.txt`; check a real open.mp server (tags in front of crashdetect lines,
   and whether its own `<code> <message>` lines are worth parsing).
7. Ideas that Phase 6 did not need: cache the result of `SourceIndex.find` per logged path;
   count entries in a source folder while listing it; make `sanitize()` clamp a negative limit.

Deliberately not done in Phase 6: new features, a redesign, new dependencies, publishing.

## 12. Migration and upgrade notes

- **Signature scheme `v1`.** If the signature string ever changes, change `SIGNATURE_VERSION` in
  the same commit. Old baselines would then match nothing, every problem would look new, and
  `--fail-on-new` would fail. Plan a migration or tell users to save a new baseline.
- **JSON schemas.** The report and the baseline both carry `schema_version` 1. Adding fields is
  safe. Renaming, removing or changing meaning needs a new version. `load_baseline` accepts only
  the integer 1.
- **Sanitising rules.** Changing what `sanitize()` replaces changes every output. Golden tests
  in `test_textutil`, `test_render`, `test_hardening` and `test_rendering_hostile` will tell you.
- **Display limits.** `ARGS_DISPLAY_LIMIT` lives in `model.py`. `MAX_STORED_ARGS` must stay one
  larger, otherwise the ellipsis disappears (mutant P39).
- **Python support.** `requires-python >=3.10` and `[tool.mypy] python_version = "3.10"` must
  move together. The classifiers list 3.10 to 3.13.
- **New test files.** The files from Phase 6 are fully typed and need no mypy override. Older,
  untyped modules are listed by name in `[[tool.mypy.overrides]]` in `pyproject.toml`.
- **Mutation catalogue.** `scripts/mutants.json` matches exact source text. Run
  `python scripts/mutation_check.py --check` after a refactor and update what it reports. The file
  is `json.dumps(data, indent=1)` plus a newline.
- **Tests that need a POSIX user** (`geteuid() != 0`) are skipped as root. Several tests use
  `SIGALRM` as a deadline and raise a `BaseException`, because `TimeoutError` is an `OSError`
  and would be swallowed by the `except OSError` in the code under test.
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
python scripts/mutation_check.py --check  # does the catalogue still match the source?
python scripts/mutation_check.py S12 S13  # run a few; the whole catalogue takes about 35 minutes
python scripts/make_synthetic_log.py big.log --lines 1000000 --seed 1
```
