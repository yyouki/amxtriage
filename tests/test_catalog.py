import json
from dataclasses import asdict

import pytest

from amxtriage.plugin_catalog import (
    CatalogSnapshot,
    filter_catalog_entries,
    load_catalog,
    parse_catalog,
    render_catalog_report,
)
from amxtriage.errors import InputError


def raw_catalog(snapshot: CatalogSnapshot) -> dict[str, object]:
    return json.loads(
        json.dumps(
            {
                "schema_version": snapshot.schema_version,
                "snapshot_date": snapshot.snapshot_date,
                "entries": [asdict(entry) for entry in snapshot.entries],
            }
        )
    )


def test_packaged_catalog_has_evidence_for_every_documented_entry() -> None:
    snapshot = load_catalog()
    assert len(snapshot.entries) == 5
    assert all(entry.status == "documented" for entry in snapshot.entries)
    assert all(entry.target_server == "open.mp" for entry in snapshot.entries)
    assert all(entry.evidence for entry in snapshot.entries)
    assert all(
        evidence.url == "https://open.mp/docs/server/Installation"
        for entry in snapshot.entries
        for evidence in entry.evidence
    )
    assert all(not entry.server_versions and not entry.platforms for entry in snapshot.entries)


def test_server_and_status_filters_are_exact() -> None:
    snapshot = load_catalog()
    assert len(filter_catalog_entries(snapshot.entries, server="open.mp")) == 5
    assert filter_catalog_entries(snapshot.entries, server="sa-mp") == []
    assert len(
        filter_catalog_entries(snapshot.entries, server="all", status="documented")
    ) == 5
    assert filter_catalog_entries(snapshot.entries, status="verified") == []


def test_json_report_has_stable_schema_and_honest_limit_notes() -> None:
    snapshot = load_catalog()
    entries = filter_catalog_entries(snapshot.entries, server="open.mp")
    raw = render_catalog_report(snapshot, entries, output_format="json", server="open.mp")
    payload = json.loads(raw)
    assert payload["schema_version"] == 1
    assert payload["entry_count"] == 5
    assert payload["filters"] == {"server": "open.mp", "status": None}
    assert "runtime compatibility" in " ".join(payload["notes"])
    assert payload["entries"][0]["evidence"][0]["url"] == (
        "https://open.mp/docs/server/Installation"
    )


def test_markdown_report_links_official_release_and_evidence() -> None:
    snapshot = load_catalog()
    report = render_catalog_report(
        snapshot,
        filter_catalog_entries(snapshot.entries, server="open.mp"),
        output_format="markdown",
        server="open.mp",
        language="id",
    )
    assert "Katalog kompatibilitas plugin dan dependensi" in report
    assert "https://github.com/katursis/Pawn.CMD/releases/tag/3.4.0-omp" in report
    assert "https://open.mp/docs/server/Installation" in report
    assert "documented" in report


def test_empty_filter_does_not_claim_no_compatible_plugins_exist() -> None:
    snapshot = load_catalog()
    report = render_catalog_report(
        snapshot,
        filter_catalog_entries(snapshot.entries, server="sa-mp"),
        server="sa-mp",
        language="en",
    )
    assert "No catalog entries matched" in report
    assert "does not mean no compatible plugins" in report


def test_parse_rejects_boolean_schema_version() -> None:
    with pytest.raises(InputError, match="schema_version"):
        parse_catalog({"schema_version": True, "snapshot_date": "2026-10-27", "entries": []})


def test_parse_rejects_non_https_project_link() -> None:
    snapshot = load_catalog()
    raw = raw_catalog(snapshot)
    entries = raw["entries"]
    assert isinstance(entries, list)
    first = entries[0]
    assert isinstance(first, dict)
    first["project_url"] = "http://example.invalid/project"
    with pytest.raises(InputError, match="HTTPS URL"):
        parse_catalog(raw)


def test_parse_rejects_duplicate_entry_ids() -> None:
    snapshot = load_catalog()
    raw = raw_catalog(snapshot)
    entries = raw["entries"]
    assert isinstance(entries, list)
    entries.append(entries[0])
    with pytest.raises(InputError, match="duplicate entry id"):
        parse_catalog(raw)


def test_parse_rejects_unknown_status() -> None:
    snapshot = load_catalog()
    raw = raw_catalog(snapshot)
    entries = raw["entries"]
    assert isinstance(entries, list)
    first = entries[0]
    assert isinstance(first, dict)
    first["status"] = "guaranteed"
    with pytest.raises(InputError, match="unsupported status"):
        parse_catalog(raw)


def test_parse_rejects_entry_without_evidence() -> None:
    snapshot = load_catalog()
    raw = raw_catalog(snapshot)
    entries = raw["entries"]
    assert isinstance(entries, list)
    first = entries[0]
    assert isinstance(first, dict)
    first["evidence"] = []
    with pytest.raises(InputError, match="evidence must not be empty"):
        parse_catalog(raw)
