# amxtriage Pawn alert bridge

**Status:** source and protocol are implemented; the bridge still needs to compile in CI and be tested on a staging SA-MP/open.mp server before it can be considered runtime-verified.

This optional filterscript reads a local append-only file produced by `amxtriage watch --alert-pawn-file`. It does not open a network port or use RCON for delivery.

## Files and versions

- `amxtriage_bridge.pwn` — filterscript source.
- Compiler used by CI: Pawn compiler `v3.10.10`.
- Standard API headers used by CI: `pawn-lang/samp-stdlib` tag `0.3.7-R2-2-1`.
- The binary `.amx` is built by CI as an artifact; it is not committed to this repository.

## Installation

1. Install Python 3.10+ and install amxtriage from this checkout or package.
2. Compile `amxtriage_bridge.pwn` with the Pawn compiler and the standard SA-MP includes for the target environment. CI uses the pinned versions above; the compiler itself must be obtained from the [official Pawn compiler release](https://github.com/pawn-lang/compiler/releases/tag/v3.10.10). The includes come from the [official samp-stdlib repository](https://github.com/pawn-lang/samp-stdlib).
3. Copy the resulting `amxtriage_bridge.amx` to the server's `filterscripts/` directory.
4. Add `amxtriage_bridge` to the server's configured filterscript list, or load it through the server's normal administration procedure. The bridge does not edit server configuration automatically.
5. Start the monitor from the server working directory so the output is inside the server's `scriptfiles/` directory:

   ```bash
   amxtriage watch server_log.txt --alert-pawn-file scriptfiles/amxtriage-alerts.txt
   ```

6. Keep the watcher and game server able to read/write the same file. On POSIX systems amxtriage creates a new output file with mode `0600`; running both under the same OS account is the simplest setup. Do not loosen permissions beyond what is needed.

## What the bridge does

- Checks and parses the fixed `AMXTRIAGE1` record schema, then sends an alert only to connected players for whom `IsPlayerAdmin(playerid)` is true (RCON-authenticated admins).
- Displays the source file path in red and source line in blue, when the diagnostic contains both fields.
- Keeps file path and line number in structured fields; configurable human-readable message templates apply to the JSONL sink and cannot replace the protected location fields.
- Polls once per second and processes at most five records per tick to cap work per timer callback.
- Skips malformed records, limits field sizes, encodes delimiters and braces from log-derived text, and escapes percent signs before handing a message to the chat API.
- Starts at the file's current end if it exists when the filterscript loads, so old records are not replayed. If the file does not yet exist, the bridge waits for it and starts reading at byte offset zero.
- Does not issue bans, modify player state, or mitigate DDoS traffic. It is a diagnostic notice channel only.

The display uses the server's inline color format and keeps messages within the chat API's 144-character limit. See the [official SendClientMessage documentation](https://open.mp/docs/scripting/functions/SendClientMessage) and [official color list](https://open.mp/docs/scripting/resources/colorslist).

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
