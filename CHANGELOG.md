# Changelog

**Language / Bahasa / Idioma:** [English](CHANGELOG.md) · [Bahasa Indonesia](CHANGELOG.id.md) · [Español](CHANGELOG.es.md)

This changelog records user-visible project changes. It does not imply a stable release has been published.

## Unreleased

- Added an optional Tkinter desktop interface: `amxtriage gui`. It lets beginners select a local log, optionally add a Pawn source folder, choose an English/Indonesian/Spanish report, and save the result.
- Expanded CI to test Python 3.10–3.13 on Ubuntu and Python 3.12 on Windows and macOS. Added Windows file-rotation sharing and consistent LF text output; marked Linux host-metrics tests as Linux-only.
- Added separate SA-MP and open.mp Pawn bridge entry points. CI compiles SA-MP with Pawn compiler v3.10.10 and the pinned `samp-stdlib`, and open.mp with compiler v3.10.11 and the pinned `omp-stdlib`.
- Added Indonesian and Spanish versions of the platform/release guide and security policy, plus release, platform-support, and repository-settings guidance.
- Updated package metadata to describe the CLI and optional desktop GUI.

### Known limitations

- The Pawn bridge builds in CI, but actual in-game alert delivery still needs testing on a staging SA-MP/open.mp server.
- No automated DDoS/provider API adapter or server-side anti-cheat is included. Hosting providers do not share one universal management API; provider-specific adapters require separate validation and explicit opt-in.
- No native Android or iOS app is shipped. The GUI is for desktop environments with Tkinter.
- Compiler compatibility is verified only for the explicitly listed CI toolchains, not every historical or future Pawn compiler.
