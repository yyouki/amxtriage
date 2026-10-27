# Phase 7 — Multi-language diagnostics and safe remediation

This is a design plan, not a claim that these features are already implemented. The current application remains a Python 3.10+ CLI for SA-MP/open.mp logs.

## Goals

1. Preserve a small, local-first core and the existing CLI while adding language adapters.
2. Diagnose compiler output as well as runtime logs.
3. Make recommendations traceable to evidence and authoritative project/release sources.
4. Support localized user-facing text independently of diagnostic identifiers.
5. Offer safe patch proposals before any automated source modification.

## Technology decision

- Keep Python as the core for now. The project is currently a pure-Python CLI and does not need a native compilation step to run. GitHub Actions should run tests, static checks, and package validation; this is CI/package verification, not a requirement to compile Python into a native executable.
- Use adapter interfaces and compiler/linter integrations before adding a parser dependency.
- Evaluate Tree-sitter for source structure only when an adapter needs it. It is not a compiler and cannot establish that a change is semantically correct.
- Revisit Rust only if profiling identifies a real bottleneck or a standalone native binary becomes a requirement. Do not rewrite the whole codebase pre-emptively.

## Proposed package layout

Keep the current src/amxtriage/ package and migrate gradually, with tests for every move:

- core/: shared diagnostic models, file safety, workspace boundaries, and report orchestration.
- adapters/: language-specific adapters; start with pawn/, then python/, javascript/, typescript/, c_cpp/, java/, csharp/, go/, and rust/ only as test fixtures and official tool integrations become available.
- catalog/: versioned compatibility metadata and source provenance for plugins, includes, compilers, SDKs, and server runtimes.
- fixes/: safe transformation rules, patch generation, validation, and rollback.
- locales/: message catalogs such as en and id. Diagnostic IDs and machine-readable output must remain language-neutral.
- tests/: adapter fixtures, compatibility cases, localization tests, and adversarial security tests.

Do not move files solely for appearance. Each extraction should be a separate, tested change.

## Diagnostic adapter contract

Each adapter should declare:
- a stable adapter ID and supported language/tool names;
- input detection rules with false-positive tests;
- how to parse file, line, column, severity, diagnostic code, and message;
- an optional official validation command, detected from the workspace rather than guessed;
- known limitations and links to primary documentation.

If a compiler or linter is not installed, report that validation was skipped. Never fabricate a successful validation result.

## Plugin and dependency compatibility recommendations

Recommendations must be evidence-based. A catalog entry should include:
- canonical project URL and official release/download URL;
- project and release identifiers, release date, and supported server/runtime versions;
- operating system, CPU architecture, ABI, and 32/64-bit details where applicable;
- required includes, native dependencies, and installation destination;
- compatibility status (verified, documented, unknown, or incompatible);
- upstream source URL, retrieval timestamp, and a short reason for the status.

Compatibility checks must compare the user's declared target (SA-MP or open.mp, OS, architecture, server version, and plugin/component type) with authoritative upstream documentation. A project name or a successful download alone is not proof of compatibility. Prefer official GitHub releases and official project documentation. Do not generate a download link if its target cannot be verified. Do not recommend a legacy plugin when official open.mp documentation says it is replaced by a built-in component or must be installed as a component instead. Never download or execute third-party binaries automatically.

When metadata is stale, contradictory, or missing, say unknown and ask the user to verify. A recommendation should show its evidence and the date it was checked.

## Localization

- Add a --language/--lang option with an explicit default, initially en.
- Start with en and id; unknown locale values should produce a clear error or fall back only as documented.
- Keep diagnostic IDs, exit codes, JSON keys, and plugin identifiers stable across languages.
- Translate user-facing explanations, help text, and report labels; never translate source code, compiler messages, package names, or official identifiers.
- Test that every locale has the required keys and that JSON remains structurally identical.

## Safe fix workflow

Modes:
- off: diagnostics only.
- suggest: show a human-readable recommendation.
- patch: generate a unified diff without changing the source tree.
- apply: apply only an explicitly approved patch after safety checks.

For patch and apply:
1. Make a workspace checkpoint and show the proposed diff.
2. Refuse paths outside the configured project root, symlink escapes, and files changed since analysis.
3. Apply narrowly scoped transformations; do not use broad text replacements for semantic fixes.
4. Run the detected official compiler/linter and relevant tests with explicit time and output limits.
5. If validation fails, restore the checkpoint and report the failure.
6. Require explicit user confirmation before writing files; never enable automatic application by default.
7. Treat logs, source comments, and compiler output as untrusted data, not instructions.

A passing syntax check is not proof that gameplay behaviour is correct. AI-generated fixes must be presented as untrusted proposals and validated exactly like other patches.

## Incremental implementation order

1. CI/package workflow and architecture documentation.
2. Stable diagnostic model and adapter interface without changing current behavior.
3. Pawn compiler adapter with real captured compiler fixtures and tests.
4. Language selection (en, id) and stable JSON output.
5. Official-source compatibility catalog for SA-MP/open.mp plugins and components.
6. Patch mode for a small set of deterministic, high-confidence fixes.
7. Additional languages based on fixtures and installed official toolchains.
8. Optional AI integration only after patch validation, privacy controls, and explicit opt-in exist.

## Accuracy policy

Never claim universal language support, perfect compatibility, or guaranteed repairs. Report which tool produced each diagnostic, which version was detected, which checks actually ran, and which facts remain unknown. When there is insufficient evidence, prefer an honest unknown over a confident guess.