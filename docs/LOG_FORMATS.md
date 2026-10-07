# Log format evidence

This document records what is known about the log lines that `amxtriage` parses,
where each fact comes from, and what is still unknown. It was written during the
October 2026 audit. Nothing here is a promise about servers that were not
examined.

Evidence levels used below:

| Level | Meaning |
| --- | --- |
| **source** | Read in program source code at a named revision. |
| **plugin tests** | Expected output in crashdetect's own test suite. These are the plugin author's tests. |
| **observed** | Seen in public bug reports or forum posts. Not backed by source. |
| **inferred** | Concluded from source or reports. No sample shows it directly. |
| **unknown** | No evidence found. |

## 1. Sources

| Source | Revision | Use and limits |
| --- | --- | --- |
| crashdetect, fork `Y-Less/samp-plugin-crashdetect` | `2bb17d3` (tag v4.22), full history cloned | Source of every crashdetect format. The original `Zeex/samp-plugin-crashdetect` repository answered HTTP 404 during the audit, so the fork was used. The commit ids `a537639` and `efbe179` named by the previous handoff are not objects in this clone and could not be re-verified. Line numbers cited in the previous handoff do match this clone. |
| crashdetect test suite | `tests/*.pwn` at `2bb17d3`, `tests/*/output.txt` at tag v4.15 | Expected plugin output. Some expectations name the real server binary (`samp03svr`, `samp-server.exe`) as the module of `CallLocalFunction`, so they were written against the real server. The test harness itself was not read. |
| open.mp | `b6de2f2ac2ae885ec6527ade2298cdb0896ec188` (same revision as the previous handoff) | Only `Server/Components/Pawn` and `Server/Source` were checked out. Other components were not read. |
| SA-MP server | not inspected | Closed source. Its output is known only from the crashdetect test suite and from public reports. |
| Public reports | listed in the appendix | Pages were read as format evidence only. No text was copied. Every fixture in this repository was retyped with invented script, function and player names. |

## 2. Verified from source: crashdetect output

All line numbers refer to `src/` of revision `2bb17d3` unless a tag is given.

### 2.1 Prefix

`LogDebugPrint` passes the prefix `[debug] ` to `Log::PrintV` (`log.cpp:30-84`, `log.cpp:100`). Two branches exist.

| Setting | Resulting line |
| --- | --- |
| `crashdetect_log` not set (default) | `[debug] <message>` is handed to the server's `logprintf`. The server adds its own timestamp when it writes `server_log.txt`. |
| `crashdetect_log` set to a path | `<strftime(logtimeformat)> <message>` is appended to that file. There is **no** `[debug]` prefix. If the time format is empty the timestamp and the space are omitted. |

`logtimeformat` is read from `server.cfg` with the default `[%H:%M:%S]` (`options.cpp:62-63`). The server uses the same option for `server_log.txt`, so users can change it.

`logprintf` is wrapped with a fixed buffer of 1024 bytes (`logprintf.cpp`), so a very long line is cut without a marker. String arguments in stack frames are cut at 80 characters and end in `...` (`amxstacktrace.cpp:586-588`). Strings are not escaped.

`PrintStream` (`crashdetect.cpp:66`) splits a multi-line message on `\n` and prints each part as its own log line. A string argument that contains a newline therefore splits one frame over two log lines.

### 2.2 Blocks

| Block | Header text | Source |
| --- | --- | --- |
| Runtime error | `Run time error <code>: "<message>"` | `crashdetect.cpp:356`, present since 2011-12-19 |
| Crash | `Server crashed while executing <amx name>` or `Server crashed due to an unknown error` | `:312`, `:315`, both since 2012-01-23 |
| Interrupt | `Server received interrupt signal while executing <amx name>` or `Server received interrupt signal` | `:331`, `:334`, since 2012-11-21 |
| Long callback | `Long callback execution detected (hang or performance issue)` | `:642`, present since 2020-03-21 with this text |

`<amx name>` is `fileutils::GetFileName(amx_path_)`, or the literal `<unknown>` when empty (`crashdetect.cpp:111-114`). The path finder only loads files that match `*.amx` (`amxpathfinder.cpp:84`). A crash or interrupt header therefore carries a file name that ends in `.amx` or the text `<unknown>`.

### 2.3 Detail lines

Detail lines start with one space after the prefix, so in the log there are two spaces after `[debug]`.

| Code | Detail line | Source |
| --- | --- | --- |
| 4 | `Attempted to read/write array element at index <n> in array of size <m>` or `... at negative index <n>` | `:365`, `:368`, since 2016-01-16 (tag v4.16) |
| 4 | `Accessing element at index <n> past array upper bound <m>` or `... at negative index <n>` | wording from 2012-01-22 until v4.15, absent at HEAD |
| 3 | `Stack pointer (STK) is 0x<hex>, heap pointer (HEA) is 0x<hex>` | `:385` |
| 7 | `Stack pointer (STK) is 0x<hex>, stack top (STP) is 0x<hex>` | `:389` |
| 8 | `Heap pointer (HEA) is 0x<hex>, heap bottom (HLW) is 0x<hex>` | `:393` |
| 6 | `Unknown opcode 0x<hex> at address 0x<hex>` | `:398` |
| 10 | the name of the native that failed | `:402-407` |
| 19 | one name per line for every native without an address | `:355-400` (`AMX_ERR_NOTFOUND` branch) |

No AMX backtrace follows codes 9, 19, 20 and 22.

### 2.4 Frames

AMX frame: `#<n> <hex8> in [public ]<name> (<args>)[ <automaton:state, ...>][ at <file>:<line>]` (`amxstacktrace.cpp`, `AMXStackFramePrinter::Print`).

* An unknown function is printed as `??`. The function `main` is never prefixed with `public`.
* The location is `<file>:<line>`. When the file name is empty it is `<unknown file>:<line>`.
* Without debug information there is no location and the module follows the arguments (see 2.5).
* Tags appear in names and arguments (`Float:f=1.50000`, `bool:b1=true`, `e[struct:1]=@00003f70`, `&x=@00003fe0 123`, `... <4 variable arguments>`).

Native call frame inside the AMX backtrace, by plugin version:

| crashdetect | Layout |
| --- | --- |
| up to 4.11.2 | `#<n> native <name> () [<hex8>] from <module>`, module part empty when unknown (`plugin/crashdetect.cpp:117` at v4.11) |
| 4.12 to 4.19.1 | `#<n> native <name> () from <module>` |
| 4.19.2 and later | `#<n> native <name> () in <module>` (commit `3ba8bfe`, 2018-08-30) |

Native backtrace frame: `#<n> <hex> in <symbol> () in <module>` (`from` before 4.19.2). Symbols can be mangled C++ names or `??`. A frame can also end after `??` with no parentheses.

Section labels: `AMX backtrace:` since 2012-05-06. The native section was labelled `Native backtrace:` (2012-05-06), `System backtrace:` (2012-06-24, tags v4.9 and v4.10) and `Native backtrace:` again (2013-02-20). Tags v4.9 and v4.10 contain the old label.

Tags v4.9, v4.10 and v4.10.1 print an unnamed AMX frame as `??` with no parentheses (`amxstacktrace.cpp`, `AsString`). The same function prints `????????` in place of the address when the return address is zero. That second form was seen in source only and is not parsed.

After the native section a crash block prints `Registers:` (`:499`), `Stack:` (`:523`) and `Loaded modules:` (`:537`). `amxtriage` does not use these lines.

## 3. The `Script[...]` line

Shape: `Script[<path>]: Run time error <code>: "<message>"`.

| Question | Status |
| --- | --- |
| Shape and absence of the `[debug]` tag | **plugin tests** (`tests/errors/notfound`, `tests/errors/stacklow`, `tests/bugs/orte_backtrace` at v4.15) and **observed** in many public reports (appendix) |
| It comes after the crashdetect block | **plugin tests**, **observed** |
| The code in the line is the code of the **last** block when several blocks precede it | **plugin tests** (`stacklow`: block with code 7, block with code 5, one line with code 5), **inferred** to be nested executions |
| It is printed for failures at load time and in `main()` | **plugin tests**, **observed** |
| It is printed for failures inside public callbacks | **unknown**. Every authoritative sample is a load-time or `main()` failure. Public reports of callback errors mostly show only the crashdetect block, but excerpts are partial. |
| It can appear with no crashdetect block before it | **plugin tests** (`orte_backtrace`), **observed** (servers without crashdetect print `Error: Function not registered: '<name>'` lines and then only the `Script[...]` line) |
| Two identical empty `Run time error 19` blocks before one `Script[...]` line | **observed** in several reports |
| The path inside the brackets | **observed** as relative paths such as `gamemodes/<name>.amx` and `filterscripts/<name>.amx`. Characters that are legal in file names but unusual (`]`, non-ASCII) are **unknown**. |

The SA-MP server is closed source, so none of this was checked in its code.

## 4. open.mp

Checked in `Server/Components/Pawn` and `Server/Source` at `b6de2f2`.

| Fact | Status |
| --- | --- |
| open.mp does not contain the text `Script[` and does not mention crashdetect in those directories | **source** |
| Log line layout `<timestamp> <label><message>` with default timestamp `[%Y-%m-%dT%H:%M:%S%z]` (`logging.timestamp_format`) and labels `[Debug] `, `[Info] `, `[Warning] `, `[Error] ` (`logging.use_prefix`) | **source** (`core_impl.hpp:102-104`, `:2021-2035`) |
| A legacy plugin's `logprintf` goes through `vprintLn`, which logs at the message level, so a crashdetect line should look like `[<timestamp>] [Info] [debug] Run time error ...` | **inferred** from `Plugin.cpp:473-479` and `core_impl.hpp:1920-1922`. No public log with this shape was found. |
| open.mp prints AMX errors of `main()` as `<code> <message>` (`Manager.cpp:442`) and `<message>` (`Manager.cpp:559`, `Script.hpp:127`). Timers print `SetTimer(Ex): There was a problem in calling <name>: <message>` (`timers.hpp:163`). | **source** |
| Other open.mp lines nearby: `Function not registered: <name>` (`Manager.cpp:280`), `Deprecated function <a> used. This function was replaced by <b>.` (`:291`), `Could not find:` (`:318`) | **source** |
| Chat is logged as `[chat] [<name>]: <text>` (`player_pool.hpp:552`). Other tags: `[death]`, `[kill]`, `[connection]`, `[%sjoin]`, `[%spart]` | **source** |

`amxtriage` does not parse the open.mp error forms in the fourth row. They are covered by the fixture `openmp_native_error_lines_unsupported.log`.

## 5. Answers to the ten questions of the audit

1. **Exact syntax of crashdetect runtime error output.** Section 2. Verified from source and plugin tests.
2. **Exact syntax of the `Script[...]` line.** Section 3. The shape is verified by plugin tests. Behaviour for callback errors is unknown.
3. **Spacing differences between versions.** Yes. Array wording, `from` versus `in`, the bracketed native address, the `System backtrace:` label and unnamed frames differ (2.3 and 2.4).
4. **Timestamps always present.** No. Console capture has none. The format follows `logtimeformat`. The styles `[HH:MM:SS]`, `[DD/MM/YYYY HH:MM:SS]`, `[DD/MM/YYYY - HH:MM:SS]` and `[YYYY-MM-DD HH:MM:SS]` were observed, and open.mp uses ISO 8601. Formats that do not start with a digit inside the brackets (for example `[Mon Oct 06 12:00:00]`) are not recognised as timestamps. No report shows one.
5. **Unusual characters in script names.** crashdetect prints a file name that ends in `.amx`, or `<unknown>`. For the server's `Script[...]` path nothing is known beyond ordinary relative paths. A `]` inside the path would end the match early.
6. **Unusual characters in function names.** Observed and handled: `??`, `@`-prefixed and `.`-containing names, tag prefixes (`Opcode:`, `bool:`), YSI generated names, mangled C++ symbols in native frames, `main`.
7. **Is the order guaranteed.** Within the thread that runs the script, crashdetect prints its block first and the server prints the `Script[...]` line afterwards. Nested failures print the inner block first. Other threads that log at the same time could interleave lines. No report shows this and no source forbids it.
8. **Unrelated lines between the block and `Script[...]`.** Unknown. User script output was observed before and after blocks, not inside them. The parser keeps a block open for two unrelated lines. That number is a heuristic.
9. **Additional or different forms in open.mp.** Yes, see section 4. They are not parsed.
10. **Formats the parser silently missed.** Found and fixed in this audit: native call frames with a bracketed address, module names after `from`, the label `System backtrace:`, unnamed frames without parentheses, and a second empty `Run time error 19` header that created a duplicate problem. Also fixed: false positives for a long callback header that continued with other text, for crash and interrupt headers whose script was free text, and for a runtime error header followed by extra text (section 6). Still not parsed: see section 7.

## 6. Changes made to the parser

| Change | Reason |
| --- | --- |
| Native call frames may contain `[<hex>]` after `()` | crashdetect 4.11.2 and earlier (2.4). The frame used to be dropped. |
| `from` is accepted as a module marker for AMX frames, native call frames and native backtrace frames | crashdetect 4.19.1 and earlier. The module used to be lost. |
| `System backtrace:` starts the native section | crashdetect 4.9 and 4.10. Native frames were stored as AMX frames, which could change the primary frame and the signature. |
| `#<n> <hex> in ??` is an unnamed AMX frame | crashdetect 4.10. |
| A header must match the whole line. The long callback header must equal the full text. Crash and interrupt headers need a script name that ends in `.amx` (any letter case) or is `<unknown>`. | Free text that merely started like a header was reported as an event. |
| An empty `Run time error 19` block followed by an identical header is replaced by the new header | Duplicate problem for one failure (section 3, last two rows). Only code 19 is affected, because that is the only code with evidence. The surviving event is the one that receives the script name, so its signature does not change. |
| Module names are cut at 260 characters instead of dropping the frame | Bounded field size. |

Signature version 1 and the JSON schema version 1 are unchanged. Frames that used to be dropped now appear in the `backtrace` list of the JSON output. Signatures use only the first AMX frame with a real function name, so they do not change. The removed false positives and the removed duplicate for repeated code 19 headers do remove problems that older runs reported.

## 7. Coverage

| Area | Supported and tested | Partly tested | Unknown or unsupported |
| --- | --- | --- | --- |
| crashdetect 4.12 to 4.22 blocks in `server_log.txt` | all four block kinds, all detail lines, frames, native frames | | |
| crashdetect 4.9 to 4.11 layouts | label, bracketed addresses, `??` frames | | `????????` address (source only) |
| crashdetect own log file (no `[debug]`) | runtime error, long callback | | |
| `Script[...]` after a block, after nested blocks, alone | yes | | callback errors |
| Timestamps | five styles and none | | styles that do not start with a digit |
| open.mp lines | the ISO timestamp and the `[Info]` label are accepted | the combination `[Info] [debug]` is built from source, not from a real log | open.mp's own error lines |
| Vanilla load failure | `Script[...]` line | | the missing native names in `Error: Function not registered` lines are not collected |
| Interleaving | two unrelated lines inside a block | | interleaving from other threads |
| Encodings | UTF-8, UTF-8 with BOM, CRLF | | other code pages: non-ASCII characters become `U+FFFD` |
| Frames split by a newline inside a string argument | the broken frame is dropped and the block goes on | | |
| Repeated identical headers other than code 19 | kept as separate events | | no evidence either way |
| Two non-empty blocks of code 19 before one `Script[...]` line | kept as two events | | meaning unverified |

## 8. Fixtures

`tests/fixtures/formats/` holds one `.log` file per format and `manifest.json`.
Every fixture is **synthetic**: the structure was taken from the sources above and the names were invented. The manifest states for each fixture:

* `status`: `verified-format`, `characterization` (current behaviour pinned, meaning unverified), `limitation` or `unsupported`
* `evidence`: source references and report URLs
* `events`: the expected parse result, written by hand from the format, not copied from parser output

`tests/test_format_fixtures.py` parses each fixture the way the program does and also checks that the result does not change with the read chunk size, with CRLF line endings, or with a byte order mark. To add a format: add the `.log` file, add its manifest entry with evidence, and run the tests.

## Appendix: public reports consulted

Read during the audit, not copied. Pages may change or disappear.

* https://github.com/samp-incognito/samp-streamer-plugin/issues/457
* https://github.com/samp-incognito/samp-streamer-plugin/issues/20
* https://github.com/pawn-lang/YSI-Includes/issues/485
* https://github.com/pawn-lang/YSI-Includes/issues/551
* https://github.com/nexiustailer/nex-ac/issues/45
* https://github.com/IS4Code/YSF/issues/40
* https://github.com/Zeex/samp-plugin-crashdetect/issues/11
* https://github.com/Zeex/samp-plugin-crashdetect/issues/49
* https://forum.open.mp/showthread.php?tid=1253
* https://forum.open.mp/showthread.php?tid=2028
* https://forum.open.mp/showthread.php?tid=2047
* https://forum.open.mp/showthread.php?tid=2452
* https://sampforum.blast.hk/showthread.php?tid=652839
* https://sampforum.blast.hk/showthread.php?tid=669045
* https://www.sa-mp.ro/forums/topic/29731-problema-consola/
* https://www.sa-mp.ro/forums/topic/33559-run-time-error-4-array-index-out-of-bounds/
* https://www.sa-mp.ro/forums/topic/37069-ask-long-callback/
* https://pastebin.com/ny1v35ie
* https://pastebin.com/2HK4p1AR
* https://pastebin.com/ycJbxBFC
* https://www.scribd.com/document/887480843/server-log
* https://www.scribd.com/document/801008163/server-log-1
