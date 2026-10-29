# Contributing to amxtriage

**Language / Bahasa / Idioma:** [English](README.md) · [Bahasa Indonesia](docs/README.id.md) · [Español](docs/README.es.md)

amxtriage is intended to be small, testable and safe for server operators.

## First setup

Use Python 3.10 or later. There are no mandatory runtime dependencies.

```bash
python -m venv .venv
# Linux/macOS:
. .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy
```

CI currently tests Python 3.10, 3.11, 3.12 and 3.13. This is not a promise about future Python releases or every OS architecture.

## Beginner-friendly use

After installation, run `amxtriage gui`. Choose a log file, optionally select the Pawn source folder, choose `en`, `id` or `es`, then save a text report. Use `amxtriage --help` or `amxtriage <command> --help` for CLI options.

## Code layout

| Path | Responsibility |
|---|---|
| `src/amxtriage/cli.py` | CLI command definitions and orchestration. |
| `src/amxtriage/parser.py`, `reader.py`, `analysis.py` | Bounded log reading and diagnosis. |
| `src/amxtriage/render.py`, `locales.json` | Text/Markdown/JSON output and translated report labels. |
| `src/amxtriage/gui.py` | Optional Tkinter UI reusing the same analysis core. |
| `src/amxtriage/monitoring.py` | Opt-in Linux host/process metrics. |
| `src/amxtriage/plugin_catalog.json` | Offline evidence-backed plugin/component data. |
| `integrations/pawn/` | SA-MP and open.mp bridge entry points and setup guide. |
| `tests/` | Regression, safety and compatibility tests. |
| `docs/` | Roadmap, progress, language guides and release/provider constraints. |

Keep changes small and add regression tests beside bug fixes. Prefer typed Python and avoid adding runtime dependencies without a clear reason.

## Compiler and bridge matrix

- SA-MP bridge CI compile: `pawn-lang/compiler v3.10.10` with pinned `samp-stdlib` headers.
- open.mp bridge CI compile: `openmultiplayer/compiler v3.10.11` with pinned `omp-stdlib` headers.
- These versions do not certify every Pawn compiler release. Keep both CI paths green and mark unverified targets clearly.
- A successful compile does not prove chat delivery, administrator filtering, file permissions, or impact on game-server ping. Stage-test the exact server distribution before release.

## Security and behavior rules

- Default analysis is offline and read-only. Never execute commands taken from logs or recommendations.
- Keep generated patches as previews until a user explicitly approves apply.
- Do not add hidden processes, memory injection, self-replication, silent firewall changes, or automatic punitive bans.
- Keep logs and fixtures free of passwords, RCON tokens and private player data.
- DDoS controls must be provider-specific, opt-in, audited and tested; there is no universal hosting API.

## Documentation and language updates

Update English, Indonesian and Spanish summaries when adding a user-facing feature, or clearly mark the translation as pending. Do not translate compiler messages, identifiers, JSON keys, source paths or code.

## Before opening a pull request

1. Run the tests and quality commands above.
2. Add/update regression tests and examples; do not use private production logs as fixtures.
3. Update README files and `docs/PROGRESS.md` when verified feature status changes.
4. Explain the environment tested and list anything still unverified.
