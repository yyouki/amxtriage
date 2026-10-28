# amxtriage — Multi-language diagnostics and safe server operations

**Language / Bahasa / Idioma:** [English](PHASE7_MULTILANGUAGE.md) · [Bahasa Indonesia](PHASE7_MULTILANGUAGE.id.md) · [Español](PHASE7_MULTILANGUAGE.es.md)

**Status snapshot:** 2026-10-28. This document is a roadmap and design contract. Unless a feature is listed under “Implemented today”, do not assume it exists in the shipped CLI.

## Implemented today

- Python 3.10+ command-line tool for SA-MP/open.mp logs.
- Groups recognized AMX runtime errors, crashes and slow callbacks; supports analysis, live log following, baselines, source context and offline rule-based recommendations.
- The initial `diagnose` command parses common saved compiler/linter formats for Pawn, Python, JavaScript/TypeScript, C/C++, Java, C#, Go and Rust. It does not execute compilers and does not cover every tool/version.
- Default analysis/watch/preview operation reads local files and does not initiate network connections or modify source. Only the explicit `patch-apply` command may edit one reviewed Pawn file.
- Existing CLI recommendations are advisory. They are not proof of a correct fix.
- The offline `catalog`/`plugins` command contains nine evidence-backed records: five documented open.mp component releases, two documented legacy open.mp plugins, the upstream-documented SA-MP Streamer Plugin `v2.9.6`, and a newer `sampvoice` release marked `unknown`. Filters support server, evidence status, exact documented server version, OS/platform, CPU architecture, and installation kind. Empty metadata never implies compatibility; dependencies are not guessed.
- `patch-preview`/`fix-preview` generates a diff for one narrow Pawn compiler case. Explicit `patch-apply` requires the reviewed patch/source SHA-256 values, a private checkpoint and a trusted local Pawn compiler, plus either an operator-selected `--test-executable` (with literal repeated `--test-arg` values) or explicit `--compile-only`. Validators run without a shell and with time/output bounds. Failed compile/test validation rolls back when the target still matches the applied patch; external edits are preserved. This narrow rule is not a gameplay-correctness guarantee.

## Product target and progress accounting

The intended end state is broader than the current log triager. Track progress by feature area, not by optimism:

| Area | Current status | Completion of that area |
|---|---|---:|
| Existing SA-MP/open.mp log triage | Implemented for its documented input formats; real-server format coverage still has gaps | 100% of current v0.1 scope |
| CI, architecture and safety documentation | Cross-version tests, static checks, packaging and the pinned Pawn bridge compile job pass in GitHub Actions; live server behavior remains unverified | CI baseline implemented |
| Compiler output adapters for common formats | Initial parsers/tests for common formats are implemented; real compiler-version coverage is incomplete | First slice implemented |
| User-facing CLI/report localization | Report labels and explain headings support en/id/es; remediation advice and argparse help are still English | First slice implemented |
| Evidence-backed plugin/dependency compatibility catalog | Offline snapshot with 5 documented components, 2 documented legacy open.mp plugins, 1 documented SA-MP plugin and 1 `unknown` release (9 total); runtime verification and broader OS/version coverage remain incomplete | First slice implemented |
| In-game admin warning bridge | JSONL and `--alert-pawn-file` export, Pawn filterscript source, and CI compilation are implemented; live staging delivery is not yet verified | Implementation slice complete; staging verification pending |
| Actual network-layer DDoS mitigation / server-side anti-cheat integration | Not implemented | 0% |
| Patch generation, compile/test validation and rollback | Narrow Pawn preview plus explicit hash-confirmed apply, private checkpoint, bounded compiler/test runner or `--compile-only`, and guarded rollback; gameplay coverage remains external | First slice implemented |

The overall completion percentage must be recalculated from tested milestones. Do not count a document as implementation or a successful syntax check as proof of correct game behaviour.

## Technology and architecture

Keep the core in Python while it remains maintainable and sufficiently fast. It is a pure-Python CLI; native compilation is not required to run it. GitHub Actions should test and package it. Consider Rust only if measured profiling or a standalone native-binary requirement justifies the rewrite.

Grow the package incrementally; avoid mass file moves with no behavioural value:

- `core/`: shared diagnostic model, file-safety rules, orchestration.
- `adapters/pawn/`: first compiler/log adapter; later adapters for Python, JavaScript/TypeScript, C/C++, Java, C#, Go and Rust only when fixtures and official toolchains exist.
- `catalog/`: versioned server, plugin, component, include, compiler and dependency metadata.
- `locales/`: user-facing translations. Diagnostic IDs, JSON keys, exit codes and official identifiers remain stable across languages.
- `fixes/`: diff generation, validation, checkpointing and rollback.
- `integrations/`: explicit and independently testable alert transports.

Do not add Tree-sitter or any other parser until an adapter has a demonstrated need. A syntax tree is not a compiler and cannot establish semantic correctness.

## Localization

CLI/report labels currently support English (`en`), Indonesian (`id`) and Spanish (`es`) through `--language/--lang`. This is a first slice, not full translation: parser help and curated remediation instructions remain English; raw log/compiler text is intentionally not translated. The README language links select translated documentation.

- Extend the current explicit `--language/--lang` selection to translated parser help, complete remediation rule catalogs and all user-facing error messages, with documented fallback behaviour.
- Translate help, messages, report labels and diagnostics written by amxtriage.
- Do not translate compiler output, source code, file names, plugin names, native names or diagnostic codes.
- Keep JSON field names and schema identical across locales; localize only human-readable values.
- Test all translation keys for completeness and test locale fallback behaviour.

## Evidence-backed plugin and dependency recommendations

Every compatibility entry needs the canonical project URL, official release/download URL, source of evidence and check date, release/version, target server (SA-MP or open.mp), OS, CPU architecture, ABI/bitness where applicable, dependency requirements, installation type (plugin versus component) and a status: `verified`, `documented`, `unknown` or `incompatible`.

A download existing is not proof of compatibility. Never fabricate links, auto-download or execute third-party binaries, or label unknown versions as compatible. Prefer upstream documentation and official release pages. The bundled `amxtriage catalog` command exposes nine records: five documented component releases and two legacy plugins listed by the official open.mp installation guide, the upstream-documented SA-MP Streamer Plugin `v2.9.6`, plus one newer `sampvoice` release marked `unknown` because the guide does not list that version. The catalog records dependencies only when the cited evidence establishes them; an empty dependency list is not proof that no dependency exists. Its OS and server-version matrix is intentionally blank where the cited source does not specify it. No entry is runtime-verified by amxtriage. Check the official installation and configuration documents: https://open.mp/docs/server/Installation and https://open.mp/docs/server/config.json. If evidence is stale or contradictory, show `unknown` and explain why.

## Lightweight monitoring and trust boundaries

The desired always-on mode must be a visible, opt-in process/service—not a hidden or self-replicating “virus”. It must not inject into the game server process, tamper with memory, evade administrators, change firewall rules silently, or execute commands from log text.

Performance goals need benchmarks rather than promises:

- Tail only configured files; use bounded line/input sizes, a configurable polling interval and bounded memory.
- Deduplicate repeated incidents and apply per-signature cooldowns so one error cannot flood logs or admins.
- Use backpressure and a bounded queue; on overload, report dropped/aggregated alerts rather than slowing the game loop.
- Keep network access off by default. Any remote transport is opt-in, documented, authenticated and rate-limited.
- Run with least-privilege filesystem access and never collect player passwords or unnecessary player data.
- Measure CPU, RAM, disk I/O and alert latency on realistic logs. No software can promise zero overhead or unchanged ping on every host.

### DDoS and anti-cheat boundaries

A log analyzer can recognize symptoms or correlate server logs, but it cannot stop volumetric DDoS by itself. Actual mitigation requires appropriate network/host controls such as upstream filtering, provider mitigation, firewall/UDP policy and capacity planning. Any integration must be an explicit adapter for a supported provider or host; never claim “DDoS protected” from log monitoring alone.

Cheat detection needs server-side game rules and authoritative events. Heuristics can have false positives. Do not auto-ban on a single weak signal; use confidence levels, audit history, configurable thresholds, and a review/rollback path for punitive actions. Keep the monitor read-only until the server owner explicitly enables a documented mitigation.

## Proposed admin chat/log alert contract

The local JSONL event schema and the `--alert-pawn-file FILE` protocol are implemented. The optional filterscript at [`integrations/pawn/amxtriage_bridge.pwn`](../integrations/pawn/amxtriage_bridge.pwn) consumes the local protocol, sends alerts only to connected RCON-authenticated admins by default, and applies red file-path / blue source-line colors. Its compiler smoke test passes in GitHub Actions using the pinned Pawn compiler and standard-library revision. See the [installation guide](../integrations/pawn/README.md). **End-to-end delivery has not yet been verified on a live SA-MP/open.mp staging server**, so runtime compatibility, permissions, file rotation and actual ping/resource effects remain unverified.

Example conceptual layout:

`[AMXTRIAGE] [HIGH] gamemodes/rp.pwn:42 — Array index out of bounds`

- Owner-configurable: prefix, human-readable message template, severity labels, cooldown, and which admin/owner accounts receive the message.
- Protected parser fields: source file path and source line number must be taken from the structured diagnostic, not editable text in the message template. The template may hide/show them, but must not overwrite them.
- Display styling target: file path in red and line number in blue, using a transport-specific color representation; never treat color tags from untrusted log text as markup.
- Deliver only to authorized administrators, sanitize newlines/format controls, deduplicate and rate-limit alerts, and never send private player input or backtrace arguments by default.
- Prefer a local, permission-restricted transport. If remote RCON is ever supported, credentials must not appear in command arguments, output, logs or source control; require explicit opt-in, least privilege and strict rate limits.
- Failed alert delivery must not block the game server or the log reader.

Example target formatting token concept: `{RED}<file>{WHITE}:{BLUE}<line>{WHITE}`. Exact formatting must be tested against the selected server API before release.

## Safe correction modes

CLI modes and safety contract:

- `off`: diagnostics only.
- `suggest`: show an explanation and a likely remediation.
- `patch`: create a unified diff; do not change source files.
- `apply`: apply a patch only after explicit owner approval.

Every patch must be scoped to the project root, reject symlink/path escapes, verify the file has not changed since analysis, save a checkpoint, and show the diff. `patch-apply` requires reviewed source/patch hashes and a trusted local compiler. The operator must supply a trusted test/lint executable using `--test-executable`/repeated `--test-arg`, or explicitly choose `--compile-only`; validation runs as argv with no shell and has timeout/output caps. On failure, restore the original only if the target still matches the exact applied patch; otherwise preserve the external change, retain the checkpoint, and report rollback blocked. The selected test command can have workspace side effects, so only use a trusted command. Never automatically install plugins or execute commands from logs or recommendations.

A successful compiler run does not guarantee gameplay correctness. Regression fixtures, startup checks and staging-server tests are required. If a new error appears, preserve logs and the pre-change snapshot rather than repeatedly applying speculative edits. No honest workflow can guarantee “100% correct every time”; the goal is evidence, reproducibility and safe rollback.

## CI and implementation sequence

1. Keep cross-version Python CI, static checks, package build and installed CLI smoke test green; smoke-test the catalog resource from the installed wheel.
2. Keep the current parser behaviour stable; introduce a documented diagnostic/adapter interface with regression fixtures.
3. Add a Pawn compiler-output adapter and fixtures captured from official tool output.
4. Extend `en`/`id`/`es` localization to complete CLI help, error messages and remediation rules, with completeness tests and stable JSON.
5. Expand the upstream-evidence compatibility catalog only with verified official sources; add stale-entry checks and compatibility filters.
6. Exercise the implemented Pawn bridge on a staging SA-MP/open.mp server: verify actual chat delivery, RCON-admin filtering, red/blue colors, shared file permissions, startup/rotation/truncation and alert latency. Keep the CI compile test, but do not equate it with runtime verification.
7. Add additional language adapters only as each has real compiler fixtures and validation support.
8. Add deterministic patch mode first, then opt-in apply/checkpoint/rollback with compiler and regression validation.
9. Add DDoS-provider and anti-cheat integrations only when an explicit supported interface and security review exist.

The CI is a gate, not a guarantee. Do not mark a milestone complete until the relevant jobs and behaviour tests pass. Keep security-sensitive defaults conservative and show the project’s verified progress after every milestone.
