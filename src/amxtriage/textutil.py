import re
import unicodedata

DEFAULT_LIMIT = 300
ELLIPSIS = "..."

_BLOCKED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
_PATH_SEPARATORS = re.compile(r"[\\/]")


def sanitize(text: str, limit: int = DEFAULT_LIMIT) -> str:
    truncated = len(text) > limit
    chunk = text[:limit].expandtabs(4)
    cleaned = "".join(
        "?" if unicodedata.category(char) in _BLOCKED_CATEGORIES else char for char in chunk
    )
    if truncated or len(cleaned) > limit:
        if limit <= len(ELLIPSIS):
            return cleaned[:limit]
        return cleaned[: limit - len(ELLIPSIS)] + ELLIPSIS
    return cleaned


def inline_code(text: str, limit: int = DEFAULT_LIMIT) -> str:
    return "`" + sanitize(text, limit).replace("`", "'") + "`"


def basename(path: str) -> str:
    return _PATH_SEPARATORS.split(path.rstrip("\\/"))[-1]
