# amxtriage Pawn alert bridge

**Status:** bridge source and protocol are implemented; Pawn source compiles in GitHub Actions with the pinned toolchain. End-to-end chat delivery still needs staging-server verification.

This optional filterscript reads a local append-only file produced by `amxtriage watch --alert-pawn-file`. It does not open a network port or use RCON for delivery.

## Files and versions

- `amxtriage_bridge.pwn` — SA-MP entry point using `<a_samp>`.
- `amxtriage_bridge_openmp.pwn` — open.mp entry point using the official `<open.mp>` includes; both share the same implementation and local protocol.
- SA-MP CI compiler: `pawn-lang/compiler v3.10.10`.
- open.mp CI compiler: `openmultiplayer/compiler v3.10.11`.
- SA-MP headers: `pawn-lang/samp-stdlib` commit [`8ffb055624308b25521665b60e78b5e6e6b3717f`](https://github.com/pawn-lang/samp-stdlib/commit/8ffb055624308b25521665b60e78b5e6e6b3717f).
- open.mp headers: `openmultiplayer/omp-stdlib` commit [`17c1b0191195cb0b59a820135fbca622c84129dd`](https://github.com/openmultiplayer/omp-stdlib/commit/17c1b0191195cb0b59a820135fbca622c84129dd). CI pins both header revisions.
- A successful compiler run validates the Pawn source against these headers; it does not replace a live staging test against the exact server distribution.
- The binary `.amx` is built by CI as an artifact; it is not committed to this repository.

## Installation

1. Install Python 3.10+ and install amxtriage from this checkout or package.
2. Choose the entry point matching your server:
   - **SA-MP:** compile `amxtriage_bridge.pwn` using [Pawn compiler v3.10.10](https://github.com/pawn-lang/compiler/releases/tag/v3.10.10) and [`samp-stdlib`](https://github.com/pawn-lang/samp-stdlib).
   - **open.mp:** compile `amxtriage_bridge_openmp.pwn` using [open.mp Pawn compiler v3.10.11](https://github.com/openmultiplayer/compiler/releases/tag/v3.10.11) and [`omp-stdlib`](https://github.com/openmultiplayer/omp-stdlib).
   CI compiles both variants with pinned headers. Other compiler versions may work, but are not certified until an equivalent compile/runtime test passes.
3. Copy the resulting `amxtriage_bridge.amx` to the server's `filterscripts/` directory.
4. Add `amxtriage_bridge` to the server's configured filterscript list, or load it through the server's normal administration procedure. The bridge does not edit server configuration automatically.
5. Start the monitor from the server working directory so the output is inside the server's `scriptfiles/` directory:

   ```bash
   amxtriage watch server_log.txt --alert-pawn-file scriptfiles/amxtriage-alerts.txt
   ```

6. Keep the watcher and game server able to read/write the same file. On POSIX systems amxtriage creates a new output file with mode `0600`; running both under the same OS account is the simplest setup. Do not loosen permissions beyond what is needed.

## What the bridge does

The watcher also accepts `--alert-message-template` to customize the message body, for example `--alert-message-template \"{severity}: {message}\"`. Supported placeholders are `{severity}`, `{kind}`, `{message}`, `{code}`, `{signature}` and `{count}`. `{file}` and `{line}` are rejected in this template because the bridge reads the protected source location from separate fields; the filterscript always renders the path in red and line in blue.

- Checks and parses the fixed `AMXTRIAGE1` record schema, then sends an alert only to connected players for whom `IsPlayerAdmin(playerid)` is true (RCON-authenticated admins).
- Displays the source file path in red and source line in blue, when the diagnostic contains both fields.
- Keeps file path and line number in structured fields; configurable human-readable message templates apply to the JSONL sink and cannot replace the protected location fields.
- Polls once per second and processes at most five records per tick to cap work per timer callback.
- Skips malformed records, limits field sizes, and encodes delimiters and braces from log-derived text so player-controlled text cannot inject inline color tags. Percent signs in message text are sent literally (not doubled); the final chat buffer is bounded to 143 visible characters.
- Starts at the file's current end if it exists when the filterscript loads, so old records are not replayed. If the file does not yet exist, the bridge waits for it and starts reading at byte offset zero.
- Does not issue bans, modify player state, or mitigate DDoS traffic. It is a diagnostic notice channel only.

The display uses the server's inline color format and keeps messages within the chat API's 144-character limit. See the [official SendClientMessage documentation](https://open.mp/docs/scripting/functions/SendClientMessage) and [official color list](https://open.mp/docs/scripting/resources/colorslist).

## Staging smoke test (manual visual confirmation)

A helper appends one fixed, low-severity probe record to the exact file consumed by the bridge. It does not open a network connection and cannot observe the game chat; an operator must confirm delivery in the staging client.

1. Compile and load the filterscript on a staging server. Connect one RCON-authenticated admin and one non-admin test account.
2. Start the watcher with the same path that will be passed to the probe, for example `amxtriage watch server_log.txt --alert-pawn-file scriptfiles/amxtriage-alerts.txt`. Keep the bridge and watcher using compatible file permissions.
3. From the repository checkout, run the dry run first, then explicitly append the test record:

   ```bash
   python scripts/staging_bridge_probe.py scriptfiles/amxtriage-alerts.txt
   python scripts/staging_bridge_probe.py scriptfiles/amxtriage-alerts.txt --send --confirm-staging
   ```

   Run the command as an account allowed to write the alert file. The probe never truncates the file; on POSIX, a newly created file has mode `0600`.
4. Verify that the RCON admin sees the `STAGING-PROBE` message, the path `staging/bridge_probe.pwn` is red, line `4242` is blue, and the non-admin receives no message. Check the server console for bridge errors.
5. Verify normal startup/shutdown and read/write permissions. Do not rotate or truncate the alert file while either process is running. Keep the probe record in the append-only file until the watcher and bridge are stopped and the file can be handled according to your normal rotation procedure.

This is a manual staging probe, not an automated end-to-end assertion and not a latency benchmark. The probe script exits after writing; a zero exit code does not prove in-game delivery. Do not run `--send` against a production alert path.

## Admin access

By default the bridge uses `IsPlayerAdmin`, which restricts delivery to RCON-authenticated administrators. If the server has a different role/ACL system, replace `IsAmxTriageAdmin(playerid)` with that project's trusted server-side authorization check and recompile. Do not accept a client-supplied command, player name, chat text, or field from the alert record as proof of admin access.

## Operations and limits

- The output file is append-only while monitoring. Do not truncate, rotate, or replace it during normal operation; stop both sides and coordinate a clean restart if the file must be rotated.
- The bridge does not replay existing records after a normal start. The Python watcher itself also announces only newly observed diagnostic signatures unless configured to read from the start.
- Alert delivery depends on the watcher seeing a supported log diagnostic. If a TextDraw or another feature fails without generating a supported runtime/compiler message, this bridge cannot infer that failure automatically.
- This feature is not an anti-cheat or a DDoS mitigation system. It does not guarantee unchanged ping or zero CPU/RAM overhead. The timer/record limits are safeguards, not performance benchmarks.
- Test with a staging server before production. Check the actual server build, admin permissions, colors, line wrapping, file access, log rotation policy, and startup/shutdown. A successful Pawn compile proves syntax/type checking for that toolchain only, not end-to-end operation.
- No automatic plugin download, installation, firewall change, RCON command, or source-code modification occurs.

## References

- [Pawn compiler v3.10.10 release](https://github.com/pawn-lang/compiler/releases/tag/v3.10.10)
- [SA-MP standard include package](https://github.com/pawn-lang/samp-stdlib)
- [open.mp SendClientMessage](https://open.mp/docs/scripting/functions/SendClientMessage)
- [open.mp color list](https://open.mp/docs/scripting/resources/colorslist)
