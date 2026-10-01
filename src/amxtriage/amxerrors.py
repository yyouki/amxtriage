from dataclasses import dataclass

from amxtriage.model import EventKind


@dataclass(frozen=True, slots=True)
class AmxError:
    code: int
    name: str
    causes: tuple[str, ...]


_RECOMPILE_CAUSE = "Recompile the script with a compiler version that matches your server."

_ERRORS: tuple[AmxError, ...] = (
    AmxError(0, "(none)", ()),
    AmxError(1, "Forced exit", ()),
    AmxError(
        2,
        "Assertion failed",
        (
            "An `assert` statement in the script evaluated to false.",
            "Check the condition at the reported file and line.",
        ),
    ),
    AmxError(
        3,
        "Stack/heap collision (insufficient stack size)",
        (
            "The script ran out of stack/heap memory.",
            "Increase it with `#pragma dynamic <cells>` near the top of the script, "
            "for example `#pragma dynamic 65536`.",
            "Avoid very large local arrays and unbounded recursion.",
        ),
    ),
    AmxError(
        4,
        "Array index out of bounds",
        (
            "An array was read or written outside its valid index range.",
            "Check loop limits and any index that comes from a variable such as a player id, "
            "vehicle id or dialog listitem.",
            "The detail line under the error shows the bad index and the array size.",
        ),
    ),
    AmxError(
        5,
        "Invalid memory access",
        (
            "The script or a native used an address outside the script's memory.",
            "Typical triggers: passing an array or string of the wrong size to a native, "
            "an invalid reference argument, or earlier memory corruption.",
        ),
    ),
    AmxError(
        6,
        "Invalid instruction",
        (
            "The runtime met an instruction it cannot execute.",
            "Recompile the script with a compiler matching your server and make sure "
            "the .amx file is not corrupted.",
        ),
    ),
    AmxError(
        7,
        "Stack underflow",
        (
            "The stack pointer left its valid range.",
            "This often points to memory corruption, for example writing past the end "
            "of an array, or unbalanced `#emit` code.",
        ),
    ),
    AmxError(
        8,
        "Heap underflow",
        (
            "The heap pointer left its valid range.",
            "This often points to memory corruption, for example writing past the end of an array.",
        ),
    ),
    AmxError(9, "No (valid) native function callback", ()),
    AmxError(
        10,
        "Native function failed",
        (
            "A native function (provided by the server or a plugin) reported failure.",
            "The line under the error names the native; check the arguments passed to it "
            "and that plugin's own log output.",
        ),
    ),
    AmxError(
        11,
        "Divide by zero",
        (
            "A division or modulo by zero happened.",
            "Check divisors such as counts, averages and rates before dividing.",
        ),
    ),
    AmxError(12, "(sleep mode)", ()),
    AmxError(13, "(reserved)", ()),
    AmxError(14, "(reserved)", ()),
    AmxError(15, "(reserved)", ()),
    AmxError(
        16,
        "Out of memory",
        (
            "The runtime could not allocate memory for the script.",
            "Reduce very large global arrays or the memory used by plugins.",
        ),
    ),
    AmxError(
        17,
        "Invalid/unsupported P-code file format",
        ("The .amx file uses a format the runtime does not support.", _RECOMPILE_CAUSE),
    ),
    AmxError(
        18,
        "File is for a newer version of the AMX",
        (
            "The .amx file was built for a newer AMX version than the server supports.",
            _RECOMPILE_CAUSE,
        ),
    ),
    AmxError(
        19,
        "File or function is not found",
        (
            "The script calls a native that is not registered, or a function that does not exist.",
            "The server itself often words this error as 'File or function is not present'.",
            "When names are listed under the error, they are natives that were not registered: "
            "load the plugin that provides them or remove the calls.",
            "Check plugin load order and that plugin binaries match the platform "
            "(.dll on Windows, .so on Linux).",
        ),
    ),
    AmxError(
        20,
        "Invalid index parameter (bad entry point)",
        (
            "A public function index was invalid.",
            "Make sure callbacks referenced by name are declared `public`, "
            "and recompile after changes.",
        ),
    ),
    AmxError(21, "Debugger cannot run", ()),
    AmxError(22, "AMX not initialized (or doubly initialized)", ()),
    AmxError(23, "Unable to set user data field (table full)", ()),
    AmxError(24, "Cannot initialize the JIT", ()),
    AmxError(25, "Parameter error", ()),
    AmxError(26, "Domain error, expression result does not fit in range", ()),
    AmxError(27, "General error (unknown or unspecific error)", ()),
    AmxError(
        28,
        "Wrote to banned address naught",
        (
            "The script wrote to address 0, which crashdetect reports when its "
            "address_naught check is enabled.",
            "Look for a missing or invalid reference or array argument in the reported function.",
        ),
    ),
)

_BY_CODE = {error.code: error for error in _ERRORS}

LONG_CALL_CAUSES: tuple[str, ...] = (
    "A top-level callback ran longer than crashdetect's long_call_time setting (microseconds).",
    "Look for loops, heavy file or database work and blocking plugin calls "
    "inside the callback shown in the backtrace.",
)

CRASH_CAUSES: tuple[str, ...] = (
    "The server process crashed natively while running the script shown.",
    "The AMX backtrace shows which script function was running; the native backtrace "
    "shows the module, for example a plugin, where the crash happened.",
    "If the top frames are inside a plugin binary, update or remove that plugin.",
)


def lookup(code: int) -> AmxError | None:
    return _BY_CODE.get(code)


def all_errors() -> tuple[AmxError, ...]:
    return _ERRORS


def causes_for(kind: EventKind, code: int | None) -> tuple[str, ...]:
    if kind == "crash":
        return CRASH_CAUSES
    if kind == "long_call":
        return LONG_CALL_CAUSES
    if kind == "runtime_error" and code is not None:
        error = lookup(code)
        if error is not None:
            return error.causes
    return ()
