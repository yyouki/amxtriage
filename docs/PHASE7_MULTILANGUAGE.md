# amxtriage — Multi-language diagnostics and safe server operations

**Status snapshot:** 2026-10-27. This document is a roadmap and design contract. Unless a feature is listed under “Implemented today”, do not assume it exists in the shipped CLI.

## Implemented today

- Python 3.10+ command-line tool for SA-MP/open.mp logs.
- Groups recognized AMX runtime errors, crashes and slow callbacks; supports analysis, live log following, baselines, source context and offline rule-based recommendations.
- The initial `diagnose` command parses common saved compiler/linter formats for Pawn, Python, JavaScript/TypeScript, C/C++, Java, C#, Go and Rust. It does not execute compilers and does not cover every tool/version.
- Reads local files and does not initiate network connections or modify source files in its current mode.
- Existing CLI recommendations are advisory. They are not proof of a correct fix.

## Product target and progress accounting

The intended end state is broader than the current log triager. Track progress by feature area, not by optimism:

| Area | Current status | Completion of that area |
|---|---|---:|
| Existing SA-MP/open.mp log triage | Implemented for its documented input formats; real-server format coverage still has gaps | 100% of current v0.1 scope |
| CI, architecture and safety documentation | Foundation being added; CI must pass before calling it validated | In progress |
| Compiler output adapters for common formats | Initial parsers/tests for common formats are implemented; real compiler-version coverage is incomplete | First slice implemented |
| User-facing CLI/report localization | Report labels and explain headings support en/id/es; remediation advice and argparse help are still English | First slice implemented |
| Evidence-backed plugin/dependency compatibility catalog | Not implemented | 0% |
| In-game admin warning bridge | Not implemented | 0% |
| Actual network-layer DDoS mitigation / server-side anti-cheat integration | Not implemented | 0% |
| Patch generation, compile/test validation and rollback | Existing suggestions only; transactional patch workflow not implemented | Early design stage |

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

A download existing is not proof of compatibility. Never fabricate links, auto-download or execute third-party binaries, or label unknown versions as compatible. Prefer upstream documentation and official release pages. For open.mp, check its official installation and configuration documents: https://open.mp/docs/server/Installation and https://open.mp/docs/server/config.json. If the evidence is stale or contradictory, show `unknown` and explain why.

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

This is a specification, **not an implemented feature yet**. In-game alerts need a separately tested SA-MP/open.mp filterscript/plugin or a trusted local bridge; the current Python CLI cannot directly broadcast a message to players.

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

Planned modes:

- `off`: diagnostics only.
- `suggest`: show an explanation and a likely remediation.
- `patch`: create a unified diff; do not change source files.
- `apply`: apply a patch only after explicit owner approval.

Every patch must be scoped to the project root, reject symlink/path escapes, verify the file has not changed since analysis, save a checkpoint, and show the diff. Run the actual detected compiler/linter and relevant tests with time/output limits. If validation fails, roll back the patch and report the failure. Never automatically install plugins or execute scripts from a log or recommendation.

A successful compiler run does not guarantee gameplay correctness. Regression fixtures, startup checks and staging-server tests are required. If a new error appears, preserve logs and the pre-change snapshot rather than repeatedly applying speculative edits. No honest workflow can guarantee “100% correct every time”; the goal is evidence, reproducibility and safe rollback.

## CI and implementation sequence

1. Add cross-version Python CI, static checks, package build and installed CLI smoke test.
2. Keep the current parser behaviour stable; introduce a documented diagnostic/adapter interface with regression fixtures.
3. Add a Pawn compiler-output adapter and fixtures captured from official tool output.
4. Implement `en`/`id` CLI localization with completeness tests and stable JSON.
5. Build the upstream-evidence compatibility catalog and stale-entry checks.
6. Define the local alert event schema and test a no-network integration before adding in-game delivery.
7. Add additional language adapters only as each has real compiler fixtures and validation support.
8. Add deterministic patch mode first, then opt-in apply/checkpoint/rollback.
9. Add DDoS-provider and anti-cheat integrations only when an explicit supported interface and security review exist.

The CI is a gate, not a guarantee. Do not mark a milestone complete until the relevant jobs and behaviour tests pass. Keep security-sensitive defaults conservative and show the project’s verified progress after every milestone.
