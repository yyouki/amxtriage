import json
from dataclasses import asdict
from typing import cast

import pytest

from amxtriage.errors import InputError
from amxtriage.plugin_catalog import (
    CatalogSnapshot,
    filter_catalog_entries,
    load_catalog,
    parse_catalog,
    render_catalog_report,
)


def raw_catalog(snapshot: CatalogSnapshot) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(
            json.dumps(
                {
                    "schema_version": snapshot.schema_version,
                    "snapshot_date": snapshot.snapshot_date,
                    "entries": [asdict(entry) for entry in snapshot.entries],
                }
            )
        ),
    )


def test_packaged_catalog_distinguishes_documented_and_unknown_releases() -> None:
    snapshot = load_catalog()
    assert len(snapshot.entries) == 8
    documented = [entry for entry in snapshot.entries if entry.status == "documented"]
    unknown = [entry for entry in snapshot.entries if entry.status == "unknown"]
    assert len(documented) == 7
    assert len(unknown) == 1
    assert all(entry.target_server == "open.mp" for entry in snapshot.entries)
    assert all(entry.evidence for entry in snapshot.entries)
    assert all(
        any(
            evidence.url == "https://open.mp/docs/server/Installation"
            for evidence in entry.evidence
        )
        for entry in documented
    )
    newer_sampvoice = unknown[0]
    assert newer_sampvoice.id == "sampvoice-openmp-3.2.0-omp"
    assert newer_sampvoice.version == "v3.2.0-omp"
    assert any(
        evidence.url == "https://github.com/AmyrAhmady/sampvoice/releases"
        for evidence in newer_sampvoice.evidence
    )
    assert all(
        not entry.server_versions and not entry.platforms and not entry.architectures
        for entry in snapshot.entries
    )
    rustext = next(
        entry for entry in snapshot.entries if entry.id == "rustext-openmp-v2.0.11-nomemhack"
    )
    assert rustext.kind == "plugin"
    assert rustext.version == "v2.0.11 (nomemhack build)"
    assert rustext.install_location == "plugins"
    assert rustext.release_url == "https://github.com/ziggi/rustext/releases/tag/v2.0.11"
    assert any("nomemhack" in item.statement for item in rustext.evidence)
    keylistener = next(
        entry for entry in snapshot.entries if entry.id == "keylistener-openmp-1.1.2-pr"
    )
    assert keylistener.kind == "plugin"
    assert keylistener.install_location == "plugins"
    assert keylistener.release_url == "https://github.com/edgyaf/keylistener/releases/tag/1.1.2-pr"
    assert any(
        "does not establish a mandatory runtime dependency" in item.statement
        for item in keylistener.evidence
    )


def test_server_and_status_filters_are_exact() -> None:
    snapshot = load_catalog()
    assert len(filter_catalog_entries(snapshot.entries, server="open.mp")) == 8
    assert filter_catalog_entries(snapshot.entries, server="sa-mp") == []
    assert len(filter_catalog_entries(snapshot.entries, server="all", status="documented")) == 7
    assert len(filter_catalog_entries(snapshot.entries, status="unknown")) == 1
    assert filter_catalog_entries(snapshot.entries, status="verified") == []


def test_json_report_has_stable_schema_and_honest_limit_notes() -> None:
    snapshot = load_catalog()
    entries = filter_catalog_entries(snapshot.entries, server="open.mp")
    raw = render_catalog_report(snapshot, entries, output_format="json", server="open.mp")
    payload = json.loads(raw)
    assert payload["schema_version"] == 1
    assert payload["entry_count"] == 8
    assert payload["filters"] == {"server": "open.mp", "status": None}
    assert "runtime compatibility" in " ".join(payload["notes"])
    assert any("dependencies" in note for note in payload["notes"])
    assert "dependencies" in payload["entries"][0]
    assert payload["entries"][0]["architectures"] == []
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
    assert "https://github.com/ziggi/rustext/releases/tag/v2.0.11" in report
    assert "https://github.com/edgyaf/keylistener/releases/tag/1.1.2-pr" in report
    assert "Dependencies" in report
    assert "documented" in report
    assert "Arsitektur CPU" in report
    assert "OS / platform" in report
    assert "Versi server" in report



def test_markdown_catalog_column_headers_are_localized_for_all_supported_languages() -> None:
    snapshot = load_catalog()
    entries = filter_catalog_entries(snapshot.entries, server="open.mp")
    expected = {
        "en": ("Server versions", "OS / platform", "CPU architectures"),
        "id": ("Versi server", "OS / platform", "Arsitektur CPU"),
        "es": ("Versiones del servidor", "SO / plataforma", "Arquitecturas de CPU"),
    }
    for language, labels in expected.items():
        report = render_catalog_report(
            snapshot, entries, output_format="markdown", server="open.mp", language=language
        )
        assert all(label in report for label in labels)


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
