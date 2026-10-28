"""Evidence-backed, offline plugin/component compatibility catalog.

Catalog entries are advisory metadata. They are never downloaded or executed by this module.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from importlib.resources import files
from typing import Literal, cast
from urllib.parse import urlparse

from amxtriage.errors import InputError
from amxtriage.localization import translate as tr
from amxtriage.textutil import sanitize

CatalogStatus = Literal["verified", "documented", "unknown", "incompatible"]
CatalogKind = Literal["plugin", "component", "include", "dependency"]
CatalogServer = Literal["open.mp", "SA-MP"]
CatalogFormat = Literal["text", "markdown", "json"]

STATUSES: tuple[CatalogStatus, ...] = ("verified", "documented", "unknown", "incompatible")
KINDS: tuple[CatalogKind, ...] = ("plugin", "component", "include", "dependency")
SERVERS: tuple[CatalogServer, ...] = ("open.mp", "SA-MP")


@dataclass(frozen=True, slots=True)
class CatalogEvidence:
    url: str
    checked_on: str
    statement: str


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    id: str
    name: str
    kind: CatalogKind
    project_url: str
    release_url: str
    version: str
    target_server: CatalogServer
    server_versions: tuple[str, ...]
    platforms: tuple[str, ...]
    architectures: tuple[str, ...]
    dependencies: tuple[str, ...]
    install_location: str
    status: CatalogStatus
    checked_on: str
    evidence: tuple[CatalogEvidence, ...]
    notes: str


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    schema_version: int
    snapshot_date: str
    entries: tuple[CatalogEntry, ...]


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise InputError(f"invalid plugin catalog: {label} must be an object")
    return cast(dict[str, object], value)


def _text(record: dict[str, object], key: str, label: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"invalid plugin catalog: {label}.{key} must be a non-empty string")
    return value


def _checked_date(value: str, label: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise InputError(
            f"invalid plugin catalog: {label} must be an ISO date (YYYY-MM-DD)"
        ) from error
    if parsed.isoformat() != value:
        raise InputError(f"invalid plugin catalog: {label} must use YYYY-MM-DD")
    return value


def _https_url(value: str, label: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise InputError(f"invalid plugin catalog: {label} must be an HTTPS URL")
    return value


def _string_list(record: dict[str, object], key: str, label: str) -> tuple[str, ...]:
    value = record.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise InputError(f"invalid plugin catalog: {label}.{key} must be a list of strings")
    if any(not item.strip() for item in value):
        raise InputError(f"invalid plugin catalog: {label}.{key} must not contain empty values")
    return tuple(value)


def _evidence_list(record: dict[str, object], label: str) -> tuple[CatalogEvidence, ...]:
    value = record.get("evidence")
    if not isinstance(value, list) or not value:
        raise InputError(f"invalid plugin catalog: {label}.evidence must not be empty")
    evidence: list[CatalogEvidence] = []
    for index, item in enumerate(value):
        item_label = f"{label}.evidence[{index}]"
        row = _mapping(item, item_label)
        url = _https_url(_text(row, "url", item_label), item_label + ".url")
        checked_on = _checked_date(_text(row, "checked_on", item_label), item_label + ".checked_on")
        statement = _text(row, "statement", item_label)
        evidence.append(CatalogEvidence(url, checked_on, statement))
    return tuple(evidence)


def parse_catalog(raw: object) -> CatalogSnapshot:
    """Parse and validate catalog data before it is displayed."""
    record = _mapping(raw, "root")
    version = record.get("schema_version")
    if type(version) is not int or version != 1:
        raise InputError("invalid plugin catalog: unsupported schema_version")
    snapshot_date = _checked_date(_text(record, "snapshot_date", "root"), "snapshot_date")
    rows = record.get("entries")
    if not isinstance(rows, list):
        raise InputError("invalid plugin catalog: entries must be a list")

    entries: list[CatalogEntry] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(rows):
        label = f"entries[{index}]"
        row = _mapping(item, label)
        entry_id = _text(row, "id", label)
        if entry_id in seen_ids:
            raise InputError(f"invalid plugin catalog: duplicate entry id {entry_id}")
        seen_ids.add(entry_id)

        kind_text = _text(row, "kind", label)
        status_text = _text(row, "status", label)
        server_text = _text(row, "target_server", label)
        if kind_text not in KINDS:
            raise InputError(f"invalid plugin catalog: unsupported kind in {entry_id}")
        if status_text not in STATUSES:
            raise InputError(f"invalid plugin catalog: unsupported status in {entry_id}")
        if server_text not in SERVERS:
            raise InputError(f"invalid plugin catalog: unsupported server in {entry_id}")

        project_url = _https_url(_text(row, "project_url", label), label + ".project_url")
        release_url = _https_url(_text(row, "release_url", label), label + ".release_url")
        checked_on = _checked_date(_text(row, "checked_on", label), label + ".checked_on")
        if checked_on > snapshot_date:
            raise InputError(f"invalid plugin catalog: {label}.checked_on is after snapshot_date")
        evidence = _evidence_list(row, label)
        if any(item.checked_on > snapshot_date for item in evidence):
            raise InputError(
                f"invalid plugin catalog: {label}.evidence date is after snapshot_date"
            )

        server_versions = _string_list(row, "server_versions", label)
        platforms = _string_list(row, "platforms", label)
        architectures = (
            _string_list(row, "architectures", label) if "architectures" in row else ()
        )
        dependencies = _string_list(row, "dependencies", label) if "dependencies" in row else ()
        if status_text == "verified":
            if not server_versions or not platforms or not architectures:
                raise InputError(
                    f"invalid plugin catalog: verified entry {entry_id} must specify "
                    "server_versions, platforms, and architectures"
                )
            if not any(
                "runtime test passed" in item.statement.casefold()
                or "runtime-verified by amxtriage" in item.statement.casefold()
                for item in evidence
            ):
                raise InputError(
                    f"invalid plugin catalog: verified entry {entry_id} needs explicit "
                    "runtime verification evidence"
                )

        entries.append(
            CatalogEntry(
                id=entry_id,
                name=_text(row, "name", label),
                kind=kind_text,
                project_url=project_url,
                release_url=release_url,
                version=_text(row, "version", label),
                target_server=server_text,
                server_versions=server_versions,
                platforms=platforms,
                architectures=architectures,
                dependencies=dependencies,
                install_location=_text(row, "install_location", label),
                status=status_text,
                checked_on=checked_on,
                evidence=evidence,
                notes=_text(row, "notes", label),
            )
        )

    return CatalogSnapshot(schema_version=1, snapshot_date=snapshot_date, entries=tuple(entries))


def load_catalog() -> CatalogSnapshot:
    """Load the packaged offline snapshot; this function never accesses the network."""
    try:
        text = files("amxtriage").joinpath("plugin_catalog.json").read_text(encoding="utf-8")
    except OSError as error:
        raise InputError("cannot read the packaged plugin catalog") from error
    try:
        raw: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise InputError("the packaged plugin catalog is invalid JSON") from error
    return parse_catalog(raw)


def filter_catalog_entries(
    entries: tuple[CatalogEntry, ...] | list[CatalogEntry],
    *,
    server: str = "all",
    status: CatalogStatus | None = None,
    server_version: str | None = None,
    platform: str | None = None,
    architecture: str | None = None,
    kind: CatalogKind | None = None,
) -> list[CatalogEntry]:
    """Return entries matching exact, case-insensitive documented metadata.

    Empty or unspecified metadata never implies compatibility. A version/platform/architecture
    filter only matches if that exact value appears in the evidence-backed catalog entry.
    """
    if server not in {"all", "open.mp", "sa-mp"}:
        raise InputError("server filter must be one of: all, open.mp, sa-mp")
    if kind is not None and kind not in KINDS:
        raise InputError("kind filter must be one of: " + ", ".join(KINDS))

    def normalize_filter(value: str | None, label: str) -> str | None:
        if value is None:
            return None
        normalized = value.strip().casefold()
        if not normalized:
            raise InputError(f"{label} filter must not be empty")
        return normalized

    version_filter = normalize_filter(server_version, "server version")
    platform_filter = normalize_filter(platform, "platform")
    architecture_filter = normalize_filter(architecture, "architecture")

    def contains_exact(values: tuple[str, ...], expected: str | None) -> bool:
        if expected is None:
            return True
        return any(value.strip().casefold() == expected for value in values if value.strip())

    matched: list[CatalogEntry] = []
    for entry in entries:
        if server != "all" and entry.target_server.casefold() != server.casefold():
            continue
        if status is not None and entry.status != status:
            continue
        if kind is not None and entry.kind != kind:
            continue
        if not contains_exact(entry.server_versions, version_filter):
            continue
        if not contains_exact(entry.platforms, platform_filter):
            continue
        if not contains_exact(entry.architectures, architecture_filter):
            continue
        matched.append(entry)
    return matched


def _md(text: str, limit: int = 500) -> str:
    return sanitize(text, limit).replace("|", "\\|").replace("\n", " ")


def render_catalog_report(
    snapshot: CatalogSnapshot,
    entries: list[CatalogEntry],
    *,
    output_format: CatalogFormat = "text",
    server: str = "all",
    status: CatalogStatus | None = None,
    server_version: str | None = None,
    platform: str | None = None,
    architecture: str | None = None,
    kind: CatalogKind | None = None,
    language: str = "en",
) -> str:
    """Render stable JSON or a human-readable text/Markdown snapshot."""
    if output_format == "json":
        payload = {
            "schema_version": 1,
            "tool": {"name": "amxtriage"},
            "catalog_snapshot": snapshot.snapshot_date,
            "filters": {
                "server": server,
                "status": status,
                "server_version": server_version,
                "platform": platform,
                "architecture": architecture,
                "kind": kind,
            },
            "entry_count": len(entries),
            "entries": [asdict(entry) for entry in entries],
            "notes": [
                "Catalog records contain upstream documentation evidence, not a guarantee "
                "of runtime compatibility.",
                "Empty server_versions/platforms/architectures fields mean the cited evidence did "
                "not specify them.",
                "An empty dependencies list means this snapshot did not establish a dependency; "
                "it is not proof that no dependency exists.",
                "No downloads, network probes, or binary execution are performed.",
            ],
        }
        return json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"

    title = tr(language, "catalog_title")
    snapshot_label = tr(language, "catalog_snapshot").format(date=snapshot.snapshot_date)
    if output_format == "markdown":
        lines = [
            f"# {title}",
            "",
            snapshot_label,
            "",
            tr(language, "catalog_limit"),
            "",
        ]
        if not entries:
            lines.append(tr(language, "catalog_no_entries"))
            return "\n".join(lines) + "\n"
        header_labels = (
            "catalog_name",
            "catalog_version",
            "catalog_target",
            "catalog_server_versions",
            "catalog_platforms",
            "catalog_architectures",
            "catalog_kind",
            "catalog_status",
            "catalog_install",
            "catalog_dependencies",
            "catalog_release",
            "catalog_checked",
        )
        lines.extend(
            [
                "| " + " | ".join(_md(tr(language, key)) for key in header_labels) + " |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|",
            ]
        )
        for entry in entries:
            unknown_value = tr(language, "catalog_unknown_value")
            release = f"[official release]({entry.release_url})"
            evidence = ", ".join(
                f"[source]({item.url}) ({item.checked_on})" for item in entry.evidence
            )
            lines.append(
                "| "
                + " | ".join(
                    (
                        _md(entry.name),
                        _md(entry.version),
                        _md(entry.target_server),
                        _md(", ".join(entry.server_versions) or unknown_value),
                        _md(", ".join(entry.platforms) or unknown_value),
                        _md(", ".join(entry.architectures) or unknown_value),
                        _md(entry.kind),
                        _md(entry.status),
                        _md(entry.install_location),
                        _md(
                            ", ".join(entry.dependencies)
                            or tr(language, "catalog_dependencies_unknown")
                        ),
                        release,
                        evidence,
                    )
                )
                + " |"
            )
            lines.append("")
            lines.append(f"**{_md(entry.name)} notes:** {_md(entry.notes, 1000)}")
        return "\n".join(lines) + "\n"

    lines = [title, snapshot_label, tr(language, "catalog_limit"), ""]
    if not entries:
        lines.append(tr(language, "catalog_no_entries"))
        return "\n".join(lines) + "\n"
    for entry in entries:
        lines.extend(
            [
                f"[{entry.status.upper()}] {entry.name} {entry.version} "
                f"({entry.kind}) — {entry.target_server}",
                f"  {tr(language, 'catalog_project')}: {entry.project_url}",
                f"  {tr(language, 'catalog_release')}: {entry.release_url}",
                f"  {tr(language, 'catalog_server_versions')}: "
                + (", ".join(entry.server_versions) or tr(language, "catalog_unknown_value")),
                f"  {tr(language, 'catalog_platforms')}: "
                + (", ".join(entry.platforms) or tr(language, "catalog_unknown_value")),
                f"  {tr(language, 'catalog_architectures')}: "
                + (", ".join(entry.architectures) or tr(language, "catalog_unknown_value")),
                f"  {tr(language, 'catalog_install')}: {entry.install_location}",
                f"  {tr(language, 'catalog_dependencies')}: "
                + (", ".join(entry.dependencies) or tr(language, "catalog_dependencies_unknown")),
                f"  {tr(language, 'catalog_checked')}: {entry.checked_on}",
                f"  {tr(language, 'catalog_evidence')}: "
                + ", ".join(item.url for item in entry.evidence),
                f"  {tr(language, 'catalog_notes')}: {entry.notes}",
                "",
            ]
        )
    return "\n".join(lines)
