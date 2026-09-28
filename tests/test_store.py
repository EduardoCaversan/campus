from datetime import UTC, datetime, timedelta

import pytest

from campus.engines import correlate, freshness
from campus.models import CampusError, Fact


def item(value="2026-10-04T23:59:00-03:00", **kwargs):
    defaults = dict(
        subject="assignment:a",
        kind="assignment",
        field="due_at",
        value=value,
        source="moodle",
        external_ref="https://moodle.example/assignment/1",
    )
    defaults.update(kwargs)
    return Fact(**defaults)


def test_idempotent_sync_and_change_history(store):
    assert store.ingest([item()]) == 1
    assert store.ingest([item()]) == 0
    assert store.ingest([item("2026-10-05T23:59:00-03:00")]) == 1
    assert len(store.evidence("assignment:a")) == 2
    assert store.changes()[0]["type"] == "DEADLINE CHANGED"
    assert len(store.changes(acknowledge=True)) == 2
    assert store.changes() == []


def test_conflicting_sources_remain_visible(store):
    store.ingest([item(), item("2026-10-02T23:59:00-03:00", source="mail", external_ref="mail:1")])
    entity = store.entities("assignment")[0]
    assert entity["state"] == "CONFLICT"
    assert len(entity["fields"]["due_at"]) == 2


def test_stale_import_cannot_replace_newer_data(store):
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    store.ingest([item()])
    assert store.ingest([item("old", observed_at=yesterday)]) == 0
    assert store.facts()[0]["value"] != "old"


def test_snapshot_redaction(store, monkeypatch):
    monkeypatch.setenv("UTFPR_PASSWORD", "testing-secret-12345")
    store.ingest(
        [
            item(
                {"token": "do-not-persist", "text": "testing-secret-12345"},
                excerpt="testing-secret-12345",
            )
        ]
    )
    evidence = store.evidence("assignment:a")
    assert "testing-secret-12345" not in str(evidence)
    assert "do-not-persist" not in str(evidence)


def test_mapping_cycle_rejected(store):
    store.map("a", "b", 1, "user")
    with pytest.raises(CampusError):
        store.map("b", "a", 1, "user")


def test_correlate_requires_section_and_semester_for_auto_map(store):
    facts = []
    for subject in ("portal:course:A", "moodle:course:2"):
        for field, value in {
            "name": "Cálculo",
            "code": "AB123",
            "semester": "2026/2",
            "section": "S1",
        }.items():
            facts.append(
                Fact(
                    subject=subject,
                    kind="course",
                    field=field,
                    value=value,
                    source=subject.split(":")[0],
                    external_ref=subject,
                )
            )
    store.ingest(facts)
    assert correlate(store)[0]["confirmed"]
    assert len(store.entities("course")) == 1


def test_freshness():
    old = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    assert freshness([{"last_seen": old}])["state"] == "STALE"
