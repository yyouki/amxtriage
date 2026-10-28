**Language / Bahasa / Idioma:** [English](README.md) · [Bahasa Indonesia](docs/README.id.md) · [Español](docs/README.es.md)  
**Roadmap:** [Multi-language diagnostics and safe remediation](docs/PHASE7_MULTILANGUAGE.md)

# amxtriage

Triage tool for SA-MP and open.mp server logs. It reads the log, finds the problems that
the [crashdetect](https://github.com/AmyrAhmady/samp-plugin-crashdetect) plugin writes
(AMX runtime errors, server crashes and long callbacks), groups identical ones, counts them
and shows where they happen, optionally with the surrounding lines of your `.pwn` source.

- Standard library only. No runtime dependencies. Python 3.10 or newer.
- Reads plain text, `.gz` files and standard input. Never modifies the log.
- Does not use the network and does not start other programs.
- Status: 0.1.0, beta.

## The problem it solves

A busy server log holds thousands of lines, and one bug can repeat hundreds of times:
the same array overflow on every player update, the same missing native on every start.
amxtriage collapses those repeats into a short list, ordered by importance: crashes first,
then runtime errors by how often they happened, then long callbacks. Each entry shows the
error, the function and source line, the backtrace, when it was first and last seen, and a
hint about common causes.

```text
$ amxtriage analyze examples/sample_server_log.txt \
    --source-dir examples/gamemodes --top 2 --context 1
amxtriage 0.1.0
input  : sample_server_log.txt (56 lines)
result : 5 distinct problems; 7 event(s) seen in total

[1] CRASH while executing gamemodes/rp.amx   x1   id=71cbadfbb2ae
    where  : OnPlayerConnect  gamemodes/rp.pwn:23
    seen   : at sample_server_log.txt:40 [13:50:12]
    trace  :
      #0 native SetPlayerName  (samp-server.exe)
      #1 public OnPlayerConnect  gamemodes/rp.pwn:23
    native :
      #0 ??  (samp-server.exe)
      #1 ??  (plugins/mysql.dll)
    source : rp.pwn
        22 |     format(name, sizeof name, "Player_%d", playerid);
      > 23 |     SetPlayerName(playerid, name);
        24 |     return 1;
    hint   : The server process crashed natively while running the script shown.

[2] RUNTIME ERROR 4: Array index out of bounds   x3   id=67683d049c59
    where  : OnPlayerUpdate  gamemodes/rp.pwn:30 (x2), :31 (x1)
    script : gamemodes/rp.amx
    seen   : first sample_server_log.txt:19 [13:46:01], last sample_server_log.txt:30 [13:46:09]
    detail : Attempted to read/write array element at index 1000 in array of size 1000
    trace  :
      #0 public OnPlayerUpdate  gamemodes/rp.pwn:30
    source : rp.pwn
        29 |     new slot = GetPlayerScoreSlot(playerid);
      > 30 |     PlayerScores[slot] += 1;
        31 |     PlayerScores[slot + 1] += 1;
    hint   : An array was read or written outside its valid index range. (more: amxtriage explain 4)

... 3 more problem(s) not shown (use --top)

notes:
  - 1 interrupt signal event(s) were ignored.
```

This is the real output for the synthetic log in `examples/`.

## Installation

From a checkout of this repository:

```bash
python -m pip install .
```

Or build a wheel and install that:

```bash
python -m pip install build
python -m build
python -m pip install dist/amxtriage-0.1.0-py3-none-any.whl
```

Without installing anything:

```bash
PYTHONPATH=src python -m amxtriage analyze server_log.txt
```

The command is `amxtriage`, or `python -m amxtriage`. Human-readable report labels support English (default), Indonesian and Spanish. The detailed diagnostic explanations remain based on the original log/compiler message, and JSON keys stay stable in English.

## Saved compiler output

The `diagnose` command parses common formats from Pawn, Python, JavaScript/TypeScript, C/C++, Java, C#, Go and Rust. It reads saved output only and does not run a compiler.

```bash
amxtriage diagnose compile.log --source-language auto
amxtriage diagnose compile.log --source-language pawn --language id
amxtriage diagnose compile.log --format json -o diagnostics.json
```

The detector is based on common text formats, not every compiler release. “No diagnostics recognized” does not prove that compilation succeeded. The JSON format preserves structured `file`, `line`, `column`, `severity` and `code` fields. The current command does not change source files.

## Safe patch preview (diff only)

The `patch-preview` command can produce a reviewable diff for one narrow Pawn compiler case: error `001` reports a missing semicolon immediately before `return`, and the preceding line is a simple assignment/declaration. The source file must resolve uniquely inside `--source-dir`.

```bash
amxtriage patch-preview compile.log --source-dir . --format unified
amxtriage patch-preview compile.log --source-dir . --format json -o patch-preview.json
```

This is **not** a general automatic fixer. It never modifies source files, applies patches, downloads dependencies, or runs a compiler. Ambiguous or unsupported cases are refused. `--format unified` accepts one compiler log after wildcard expansion and prints only the diff; when no safe candidate is available, it prints the reason to standard error and exits with status `3`. A generated diff still needs review, compilation with the official Pawn compiler, and regression/gameplay tests before use.

## What it understands

amxtriage recognises these lines. A timestamp such as `[13:46:01]` and up to three leading
tags such as `[debug]` are accepted in front of them.

| Log text | Treated as |
|---|---|
| `Run time error N: "message"`, followed by `AMX backtrace:` and detail lines | runtime error |
| `Script[file.amx]: Run time error N: "message"`, printed by the server right after the block above | merged into the same event |
| `Server crashed while executing X` or `Server crashed due to an unknown error`, with AMX and native backtraces | crash |
| `Long callback execution detected (hang or performance issue)`, with an AMX backtrace | long callback |
| `Server received interrupt signal ...` | ignored: a normal stop. It is counted in the report notes |

How events become problems:

- **A problem is identified by its error code, not by the message text.** crashdetect prints
  code 19 as "File or function is not found" while the server prints "File or function is not
  present". Both describe the same problem.
- crashdetect's block and the server's `Script[...]` line are merged into one event when
  they belong together: same error code, with at most two unrelated lines between them.
- A signature (`id=` in the report) is built from the kind, the error code, the function and
  the source file *name* of the top frame (the path is dropped, so a Windows path and a Linux
  path give the same id). Without a script frame it uses the script name, the first native
  frame or, for codes 10 and 19, the missing native names. Line numbers, message text,
  counts and timestamps are not part of it.
- Only lines that *start* with the expected text count. A player cannot create a problem by
  typing `Run time error 4: ...` into the chat.

What was and was not checked against real software:

- The crashdetect formats were checked against the plugin source (commit `a537639`) and its
  test fixtures: header strings, backtrace and frame layout, `<unknown file>`, detail lines
  and the `[debug]` prefix.
- The `Script[...]` line is printed by the closed-source SA-MP server. It does not exist in
  any open-source repository that was checked, so it is the one format assumption that is
  not verified from source. Please check it against a real `server_log.txt` of your server.
- open.mp prints its own script errors as `<code> <message>` without the words "Run time
  error". Those lines are not parsed. crashdetect lines that pass through open.mp's legacy
  plugin layer are accepted, but this was not tested on a real open.mp server.

## Usage

### analyze

```text
amxtriage analyze [options] LOG [LOG ...]
```

`LOG` is a file, a `.gz` file, or `-` for standard input. Give rotated files oldest first.
A name with a wildcard (`*`, `?`, `[`) that the shell did not expand, as in Windows `cmd`,
is expanded by amxtriage itself. It is an error if nothing matches.

| Option | Meaning |
|---|---|
| `--format text\|markdown\|json` | Report format. Default `text`. |
| `--language en\|id\|es`, `--lang` | Human-readable report label language: English, Indonesian or Spanish. Default `en`. Works before or after the subcommand. |
| `-o FILE`, `--output FILE` | Write the report to FILE (UTF-8) instead of the terminal. A symbolic link, or a file with more than one hard link, is refused (see "Security and privacy"). |
| `--top N` | Show at most N problems. Default 20. |
| `--min-count N` | Hide problems that happened fewer than N times. |
| `--kind runtime_error\|crash\|long_call` | Show only this kind. Can be repeated. |
| `--source-dir DIR` | Folder with your `.pwn`/`.inc` files. Shows the source around each problem. |
| `--context N` | Source lines above and below. Default 3, 0 turns it off, at most 20. |
| `--baseline FILE` | Hide problems that are already listed in this baseline. |
| `--save-baseline FILE` | Write every problem found in this run to FILE. |
| `--fail-on-new` | Exit with status 1 if problems outside the baseline exist. Needs `--baseline`. |
| `--show-args` | Include function arguments in backtraces. Read the privacy section first. |

Examples:

```bash
amxtriage analyze server_log.txt
amxtriage analyze server_log.1.gz server_log.txt --top 10
cat server_log.txt | amxtriage analyze -
amxtriage analyze server_log.txt --kind crash --min-count 2
amxtriage analyze server_log.txt --format markdown -o report.md
amxtriage analyze server_log.txt --format json > report.json
```

`--top`, `--min-count` and `--kind` only change what is shown. A saved baseline always
contains every problem of the run.

### Source context

With `--source-dir`, amxtriage prints the lines around the failing line.

Logs contain paths from the machine that compiled the script, such as
`C:\work\gamemodes\rp.pwn`, so they never match your folder exactly. amxtriage therefore
builds an index of the files under `--source-dir` (extensions `.pwn`, `.inc`, `.p`, `.pawn`)
and looks the logged path up *by name*: the file name must match, the longest matching path
ending wins, and if two files tie, no snippet is shown. The path from the log is never opened.

### Baselines

A baseline is the list of problems you already know about. It lets you see only what is new.

```bash
amxtriage analyze today.log --save-baseline baseline.json
amxtriage analyze tomorrow.log --baseline baseline.json --fail-on-new
```

The second command prints only the problems that are not in `baseline.json` and exits with
status 1 if there are any, so it can gate a deployment or a cron job. It exits 0 when
nothing is new. A baseline stores, for each problem, the id, kind, error code, function
name and count. It stores no arguments, file paths or player data.

Signature ids are the first 12 hex digits of a SHA-256 hash of the signature described above,
with a version prefix (`v1`). A test pins the id of a known problem, so baselines keep
working between releases. If the scheme ever changes, the prefix must change with it.

A baseline file is a UTF-8 JSON object of at most 10 MiB with `tool` (`"amxtriage"`),
`schema_version` (the integer `1`) and `signatures` (a list of objects, each with an `id` of
12 hexadecimal digits). Other fields are ignored. One leading byte order mark is accepted,
because some Windows editors add it. A baseline is refused with exit status 2, and never
treated as an empty one, when it is not valid JSON, is nested too deeply, contains a number
with more than 32 digits, contains `NaN` or `Infinity`, has a `schema_version` that is not
the integer 1 (`true`, `1.0` and `"1"` are refused), or has a bad `id`. The message names
the problem and does not repeat values from the file. If a key appears twice, the last one
counts, as in most JSON readers. A named pipe is read like a file, up to the size limit, so
`--baseline <(git show main:baseline.json)` works.

### watch

```text
amxtriage watch [--from-start] [--poll-interval SECONDS] [--source-dir DIR]
                [--context N] [--show-args] [--baseline FILE]
                [--alert-jsonl FILE] [--alert-pawn-file FILE]
                [--alert-prefix TEXT] [--alert-template TEMPLATE] LOG
```

Follows a growing log, like `tail -f`. Each new problem is printed once, the first time it
appears. When you press Ctrl+C (or the process gets SIGTERM) it prints a summary and exits 0.

```text
$ amxtriage watch --from-start examples/sample_server_log.txt
watching sample_server_log.txt, checking every 1s; press Ctrl+C to stop
NEW  RUNTIME ERROR 19: File or function is not found   x1   id=a4a81fe6b09b
    script : gamemodes/rp.amx
    seen   : at sample_server_log.txt:11 [13:45:01]
    detail : sscanf
    detail : mysql_connect
    hint   : The script calls a native that is not registered, or a function that does not exist. (more: amxtriage explain 19)
...
```

The banner goes to standard error, the problems to standard output.

- Only lines written after the start are read, unless `--from-start` is given.
- `--poll-interval` is between 0.1 and 60 seconds. The default is 1.0.
- Log rotation (the file is replaced) and truncation (the file shrinks) are followed.
- Problems listed in `--baseline` are not announced.
- When the log goes quiet, a problem block that is still open is closed and announced, so the
  last problem does not wait for another line.
- `watch` does not read `.gz` files or standard input.

#### Structured local alert export

`watch` can append new diagnostic events to a local JSONL file for a separately configured bridge:

```bash
amxtriage watch server_log.txt --alert-jsonl ./scriptfiles/amxtriage-alerts.jsonl
amxtriage watch server_log.txt --alert-jsonl alerts.jsonl \\
  --alert-prefix OWNER --alert-template "{prefix} {severity}: {message}"
```

The JSONL option is a local event stream, not itself an in-game sender. For a local SA-MP/open.mp chat bridge, use the optional Pawn filterscript below. The JSONL template changes summary text only; structured `source.file` and `source.line` fields remain separate and cannot be set by template text. The event includes target presentation metadata (file red, line blue). Unsafe link/non-regular-file targets are refused, and a write failure disables only alert export while log following continues. Player arguments/backtraces are not sent by default.

Template fields are restricted to `{prefix}`, `{severity}`, `{kind}`, `{message}`, `{file}`, `{line}`, `{code}`, `{signature}`, and `{count}`. Newlines, unknown fields, attribute access, conversions and format specifications are rejected.

#### Optional Pawn in-game chat bridge

The source is at [`integrations/pawn/amxtriage_bridge.pwn`](integrations/pawn/amxtriage_bridge.pwn); setup and caveats are in [the bridge README](integrations/pawn/README.md).

```bash
amxtriage watch server_log.txt --alert-pawn-file ./scriptfiles/amxtriage-alerts.txt
```

Compile the filterscript using the [pinned Pawn compiler](https://github.com/pawn-lang/compiler/releases/tag/v3.10.10) and the standard includes documented in the bridge guide, then copy the resulting `.amx` to `filterscripts/` and load it explicitly through the server's normal configuration. The bridge polls once per second and processes at most five records per tick. By default, only RCON-authenticated admins receive the message. The file path is shown in red and the source line in blue. Run the watcher and server with compatible file permissions; on POSIX, newly created alert files use mode `0600`.

**Verification status:** the Pawn source compiles in GitHub Actions, but has not yet been end-to-end tested on a live SA-MP/open.mp staging server. Compilation does not prove runtime compatibility or unchanged ping. The bridge is a diagnostic alert channel—not DDoS mitigation or anti-cheat, and it does not ban players or alter the game state.

### explain

```text
$ amxtriage explain 4
AMX error 4: Array index out of bounds

Common causes and checks:
  - An array was read or written outside its valid index range.
  - Check loop limits and any index that comes from a variable such as a player id, vehicle id or dialog listitem.
  - The detail line under the error shows the bad index and the array size.

These are common causes, not a diagnosis. The backtrace in the log is the evidence.
```

`amxtriage explain` without a code lists all known codes. The hints are general advice, not
a diagnosis.

### catalog (alias: plugins)

List the bundled offline compatibility evidence for plugins/components:

```bash
amxtriage catalog
amxtriage catalog --server open.mp
amxtriage catalog --server open.mp --format markdown -o plugin-catalog.md
amxtriage plugins --format json -o plugin-catalog.json
```

Each entry contains the official project/release links, target server, installation location, evidence URL/date, and a status (`verified`, `documented`, `unknown`, or `incompatible`). The current snapshot has documented open.mp component entries from the official installation guide. `documented` means the upstream guide lists the release; it is **not a claim of runtime testing**. Empty version/platform fields mean the cited source did not specify those values. This command is fully offline: it does not check live releases, download binaries, or install components. Unknown evidence must remain `unknown` instead of being guessed.

### recommend (alias: suggest)

```bash
amxtriage recommend server_log.txt --source-dir ./gamemodes
amxtriage suggest server_log.txt --format markdown -o recommendations.md
amxtriage recommend server_log.txt --format json -o recommendations.json
```

`recommend` uses an offline rule catalog to prioritise common AMX runtime errors, crashes, and
long callbacks. For known issues it gives targeted checks and, for a few common cases, an
illustrative Pawn pattern such as an array bounds guard or a divide-by-zero guard. With
`--source-dir`, it also includes the matching source context when the log supplies a unique
file-and-line location. `--top`, `--min-count`, and `--context` work as they do for `analyze`.

The snippets are **templates, not generated fixes**: names such as `index`, `values`, and
`divisor` are placeholders. A log rarely contains enough information to infer the intended game
logic safely. This command never changes source files, contacts a remote service, or runs a
compiler. It labels uncertain guidance with a confidence level and describes the checks to make.
The JSON output is a separate schema (`schema_version: 1`, `mode: rule-based-recommendations`)
and explicitly states that no automatic changes were applied.

Automatic source repair is intentionally not part of this release. A future repair provider must
produce a reviewable patch, verify that target files remain inside the chosen source directory,
make backups, and run a configured compiler/test command before retaining changes. It should be
opt-in; a server-side SA-MP plugin is not the right mechanism for editing `.pwn` files. The
appropriate extension point is a local analysis/repair provider, optionally backed by a rule pack
or an explicitly enabled AI service.

## Output formats

- **text**: readable in a terminal. Default.
- **markdown**: headings, fenced blocks for backtraces. Paste it into an issue or a chat.
- **json**: for scripts. `schema_version` is 1. Top-level keys: `schema_version`, `tool`,
  `summary`, `notes`, `problems`.
  - `summary`: `sources`, `lines_read`, `truncated_lines`, `events`, `dropped_events`,
    `ignored_interrupts`, `matching_problems`, `shown_problems`, `omitted_problems`,
    `known_hidden`, `baseline_used`.
  - each problem: `id`, `kind`, `code`, `message`, `script`, `function`, `file`, `count`,
    `lines`, `first`, `last`, `details`, `backtrace`, `native_backtrace`, `causes`, `source`,
    `new`. Arguments appear in `backtrace` only with `--show-args`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. With `--fail-on-new`: nothing new. `watch` also exits 0 on Ctrl+C. |
| 1 | `--fail-on-new` found problems that are not in the baseline. |
| 2 | Error: file cannot be read, binary input, bad baseline, bad option, a report file that cannot be written, or an internal error. An internal error prints `error: internal error (...)` and the places in the code. It is a bug: please report it. |
| 130 | `analyze` was interrupted with Ctrl+C. |

Status 1 is reserved for new problems. A crash of amxtriage itself ends with 2, so a pipeline
never mistakes a bug for a finding.

## Security and privacy

amxtriage reads logs that can contain text from players. It is built so that this text cannot
leak secrets or attack your terminal, within the limits listed below. This is a list of
mitigations and their limits, not a guarantee.

What it does:

- **Function arguments are hidden by default.** crashdetect prints string arguments as they
  are, so the `inputtext` of a login dialog (a password) can end up in a backtrace.
  Arguments are shown only with `--show-args`, are never stored in a baseline, and the
  option's help text warns not to share that output.
- **Text from logs is sanitised before it is printed.** Control characters (including ESC and
  the C1 range), bidirectional and other format characters, line and paragraph separators,
  private-use and unassigned characters are replaced by `?`. This covers text, Markdown and
  the string values inside JSON, and also file names that appear in messages. Tabs become
  spaces. Backticks are neutralised in Markdown.
- **Paths found in a log are never joined to the filesystem.** They are only keys that are
  looked up in an index built from a real listing of `--source-dir`. A symlink that points
  outside that folder is rejected, symlinked directories are not followed, and only regular
  files up to 8 MiB are read. On systems that have `O_NOFOLLOW`, `O_DIRECTORY` and `dir_fd`
  (tested on Linux only) the file is then opened starting from the source folder, one path
  component at a time, with `O_NOFOLLOW` (a symlink
  anywhere in the path is refused) and `O_NONBLOCK` (a named pipe cannot block). The open
  file is checked again with `fstat`: it must be a regular file within the size limit and the
  same file (device and inode) that was checked. At most 8 MiB are read, line by line. So
  replacing a file after the check does not make amxtriage read a file outside the folder.
- **Memory is bounded.** Lines are cut at 8,192 bytes, input is read in 1 MiB chunks, and
  there are caps of 5,000 problems, 48 AMX frames and 16 native frames per event, and 64
  line numbers per problem. Beyond the cap, events are counted and reported in the notes
  instead of being stored. The arguments of a frame are stored up to 401 characters; a report
  never shows more than 400. Bounded does not mean small: a log built to reach every cap at
  once (5,000 different problems, 48 frames each, every stored field at its limit) needed
  320 MB in the test under "Performance", where ordinary logs need about 25 MB.
- **Binary input is refused** (a NUL byte in the first 4,096 bytes, or a UTF-16 byte order
  mark at the start). Invalid UTF-8 is replaced, not fatal. A damaged `.gz` file is a clean error.
- **No network, no subprocesses, no dynamic code.** The package imports no networking module
  (a test checks this) and `src/` contains no `subprocess`, `eval` or `pickle`.
- **Writes only where you tell it to**: `-o FILE` and `--save-baseline FILE`. A baseline is
  written to a temporary file in the same folder and then moved into place, which replaces a
  symbolic link or a hard-linked name instead of writing through it. `-o` opens the file with
  `O_NOFOLLOW`, so a symbolic link as the file name is refused (this includes
  `-o /dev/stdout`: leave `-o` out or redirect the output instead), and a file that has more
  than one hard link is refused before anything is changed. Devices such as `/dev/null` still
  work.
- **A bug cannot look like a finding.** An unexpected exception ends with status 2 and a short
  message that names the exception type and the places in the code. It never prints the text
  of the exception, which could contain data from the log.

Limits you should know:

- A person who can put a newline into text that the server logs can forge a whole log line.
  The tool cannot tell a forged line from a real one. A forged line can at most add or
  change a problem in the report.
- A `.gz` file has no limit on its decompressed size. Memory stays flat, but time grows with
  the size: measured here, a 1 MiB file that expands to 1 GiB took about 2.6 s, and a 10 KB
  file with 5 million short lines took about 2 s. For archives you do not trust, run it under
  `timeout` or `ulimit -t`.
- Someone with write access to your `--source-dir` can still change what a snippet shows, by
  changing the file. On Linux they can no longer make amxtriage read a file outside the
  folder by swapping one (see above); other POSIX systems were not tested. Windows has no
  `O_NOFOLLOW`: there the file is
  opened by path and only the `fstat` checks apply, which narrows the window but does not
  close it. That path is simulated by tests on Linux and has not been run on Windows. A hard
  link to a file outside the folder cannot be told from a normal file. Do not point
  `--source-dir` at a folder that untrusted users can write to.
- `-o` checks only the last part of the path: a symbolic link in a folder name is followed,
  and on Windows symbolic links are followed everywhere.
- A baseline can be up to 10 MiB. A file of that size full of the shortest possible entries
  (476,617 of them) took about 0.5 s and 158 MB of memory to read. A named pipe given as a
  baseline waits for its writer.
- There is no cap on the number of entries in one `--source-dir` folder. A folder with
  400,000 files took about 2 s and 80 MB of memory in total to index. If thousands of files
  share one name, every lookup compares all of them (about 20 ms for 32,000), which matters
  only with a very large `--top`.
- `--show-args` output can contain passwords. Do not post it.
- Reports show error messages, function names and file paths exactly as the log has them, after
  sanitising. Read a report before you publish it.

## Performance

Measured on one 1-CPU Linux VM with Python 3.12.3. These are measurements, not promises.

| Test | Result |
|---|---|
| Start-up (`explain 4`, median of 15) | 81 ms, while an empty Python takes 21 ms |
| 1,000,000 lines, 55.9 MB (text, JSON, Markdown, `.gz`, stdin) | 1.6 to 1.7 s, about 600,000 lines/s, 25 MB peak memory |
| 895 MB, 16 million lines | 24 s, 24.7 MB peak memory (the same as for 56 MB) |
| 300,000 distinct problems (60 times the cap) | 8.4 s, 31.5 MB, 295,000 events reported as not grouped |
| 600,000 distinct problems (120 times the cap) \* | 18 s, 31 MB |
| 5,000 problems of 48 frames with 8,000-character arguments, a hostile log \* | 178 MB, 5.7 s. Before the argument limit: 1,924 MB, 7.3 s |
| The same, with every other stored field at its limit as well \* | 320 MB, 7.6 s. Before: 1,917 MB, 18 s |
| 1,000,000 events in one problem, 265 MB | 28 s, 24.4 MB (about 35,000 events/s) |
| A single 200 MB line | 0.18 s, 21 MB |
| `watch`, announcement delay after a write (24 samples) | 24 to 989 ms with the default 1.0 s poll |
| `watch`, idle for 10 s | 0.07 s of CPU, which is the start-up cost |

Logs full of errors are slower per line than logs with a few errors, because every error is
parsed and grouped.

Rows marked with an asterisk were measured in a later session on another 1-CPU VM with
Python 3.12.3. On that VM a log of 2,000,000 lines (117 MB) took 3.3 s, and the version before
the security changes took 3.4 to 3.9 s, so the changes did not make it slower.

## Limitations

- Tested on Linux with Python 3.10, 3.11, 3.12 and 3.13. Windows and macOS were not tested.
  Opening source files without following links and refusing symbolic links in `-o` need
  `O_NOFOLLOW`, which Windows does not have; see "Security and privacy".
- Formats: see "What it understands" for the `Script[...]` line and for open.mp.
- crashdetect's block and the server's `Script[...]` line are merged only when at most two
  unrelated lines lie between them. In `watch`, a long pause between the two could split them
  into two events.
- `watch` cannot see a file that is truncated and grows past its old size between two polls,
  and it does not follow a rotation into a `.gz` file.
- The check for binary input looks only at the first 4,096 bytes.
- Hints from `explain` are general. The backtrace in the log is the evidence.
- `recommend` provides deterministic playbook guidance, not a semantic Pawn compiler. It never auto-edits files or verifies a suggested pattern by compiling it.

## Development

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"

pytest
ruff check .
ruff format --check .
mypy
python -m build
```

Layout:

| Path | Purpose |
|---|---|
| `src/amxtriage/reader.py` | Streaming line reader: files, gzip, stdin, line cap, binary check |
| `src/amxtriage/parser.py` | Turns lines into events (runtime error, crash, long call) |
| `src/amxtriage/aggregate.py` | Signatures and grouping, with caps |
| `src/amxtriage/analysis.py` | Runs reader, parser and aggregator; builds the report |
| `src/amxtriage/render.py` | Text, Markdown and JSON analysis reports |
| `src/amxtriage/recommendation.py` | Offline remediation rules and recommendation output; never writes source files |
| `src/amxtriage/source.py` | Safe source lookup and snippets |
| `src/amxtriage/baseline.py` | Saving and loading baselines |
| `src/amxtriage/output.py` | Writing a report file without following links |
| `src/amxtriage/follow.py` | Following a live log (rotation, truncation) |
| `src/amxtriage/textutil.py` | `sanitize()` and helpers |
| `src/amxtriage/amxerrors.py` | AMX error codes and hints |
| `src/amxtriage/cli.py` | Commands and options |
| `tests/` | Test suite |
| `examples/` | A synthetic log and a small gamemode |
| `scripts/make_synthetic_log.py` | Writes a large synthetic log for performance tests |
| `scripts/mutation_check.py` | Breaks the code on purpose and checks that the tests notice |

Notes for contributors:

- A new test file must be added to the module list in `[[tool.mypy.overrides]]` in
  `pyproject.toml`. If you forget, mypy fails and tells you.
- `examples/sample_server_log.txt` is synthetic. It is built from the verified formats but is
  not a real server log.
- Large synthetic log: `python scripts/make_synthetic_log.py big.log --lines 1000000 --seed 1`.
- Mutation check: `python scripts/mutation_check.py` (about 35 minutes on one CPU; one shell
  command may be limited to 300 s, so run it in chunks of about 24 ids), or give mutant ids
  to run a few. `--check` verifies that the catalogue still matches the source.
- `HANDOFF.md` has the project state, design decisions and open work for the next person.

## License

MIT. See `LICENSE`.
