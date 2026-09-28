import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from campus.models import CampusError, Fact, ProviderResult, now
from campus.security import clean, digest, safe_url

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO meta VALUES ('schema_version','1');
CREATE TABLE IF NOT EXISTS snapshots (
 id TEXT PRIMARY KEY, content TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
 id INTEGER PRIMARY KEY, subject TEXT NOT NULL, kind TEXT NOT NULL, field TEXT NOT NULL,
 value TEXT NOT NULL, source TEXT NOT NULL, external_ref TEXT NOT NULL,
 observed_at TEXT NOT NULL, confidence REAL NOT NULL, snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
 version_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS current (
 subject TEXT NOT NULL, field TEXT NOT NULL, source TEXT NOT NULL, external_ref TEXT NOT NULL,
 evidence_id INTEGER NOT NULL REFERENCES evidence(id), last_seen TEXT NOT NULL,
 PRIMARY KEY(subject,field,source,external_ref)
);
CREATE TABLE IF NOT EXISTS changes (
 id INTEGER PRIMARY KEY, subject TEXT NOT NULL, field TEXT NOT NULL, type TEXT NOT NULL,
 old_evidence INTEGER REFERENCES evidence(id), new_evidence INTEGER NOT NULL REFERENCES evidence(id),
 detected_at TEXT NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS provider_health (
 provider TEXT PRIMARY KEY, state TEXT NOT NULL, authenticated INTEGER,
 message TEXT NOT NULL, checked_at TEXT NOT NULL, last_success TEXT
);
CREATE TABLE IF NOT EXISTS mappings (
 alias TEXT PRIMARY KEY, canonical TEXT NOT NULL, confidence REAL NOT NULL,
 reason TEXT NOT NULL, confirmed INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL, report_path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS evidence_subject ON evidence(subject,field);
CREATE INDEX IF NOT EXISTS change_time ON changes(detected_at);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=15)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(SCHEMA)
        version = self.connection.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()[0]
        if version != "1":
            raise CampusError("Unsupported database schema version; do not downgrade this database")

    def close(self):
        self.connection.close()

    @contextmanager
    def transaction(self):
        with self.connection:
            yield

    def ingest(self, facts: list[Fact]) -> int:
        count = 0
        with self.transaction():
            for original in facts:
                fact = Fact.model_validate(clean(original.model_dump()))
                fact.external_ref = safe_url(fact.external_ref)
                value = json.dumps(fact.value, sort_keys=True, ensure_ascii=False, allow_nan=False)
                snapshot = {
                    "excerpt": fact.excerpt,
                    "value": fact.value,
                    "external_ref": fact.external_ref,
                }
                sid = digest(snapshot)
                version = digest(
                    {"value": fact.value, "confidence": fact.confidence, "snapshot": sid}
                )
                key = (fact.subject, fact.field, fact.source, fact.external_ref)
                previous = self.connection.execute(
                    "SELECT e.*, c.last_seen FROM current c JOIN evidence e ON e.id=c.evidence_id WHERE c.subject=? AND c.field=? AND c.source=? AND c.external_ref=?",
                    key,
                ).fetchone()
                if previous and fact.observed_at < previous["last_seen"]:
                    continue  # An older import must not roll back a newer source observation.
                if previous and previous["version_hash"] == version:
                    self.connection.execute(
                        "UPDATE current SET last_seen=? WHERE subject=? AND field=? AND source=? AND external_ref=?",
                        (fact.observed_at, *key),
                    )
                    continue
                self.connection.execute(
                    "INSERT OR IGNORE INTO snapshots VALUES (?,?,?)",
                    (sid, json.dumps(snapshot, ensure_ascii=False), now()),
                )
                cursor = self.connection.execute(
                    "INSERT INTO evidence(subject,kind,field,value,source,external_ref,observed_at,confidence,snapshot_id,version_hash) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        fact.subject,
                        fact.kind,
                        fact.field,
                        value,
                        fact.source,
                        fact.external_ref,
                        fact.observed_at,
                        fact.confidence,
                        sid,
                        version,
                    ),
                )
                eid = cursor.lastrowid
                self.connection.execute(
                    "INSERT OR REPLACE INTO current VALUES (?,?,?,?,?,?)",
                    (*key, eid, fact.observed_at),
                )
                if not previous or previous["value"] != value:
                    label = (
                        "NEW " + fact.kind.upper()
                        if not previous
                        else {
                            "due_at": "DEADLINE CHANGED",
                            "absences": "ATTENDANCE CHANGED",
                            "grade": "NEW GRADE",
                        }.get(fact.field, fact.field.upper() + " CHANGED")
                    )
                    self.connection.execute(
                        "INSERT INTO changes(subject,field,type,old_evidence,new_evidence,detected_at) VALUES (?,?,?,?,?,?)",
                        (
                            fact.subject,
                            fact.field,
                            label,
                            previous["id"] if previous else None,
                            eid,
                            now(),
                        ),
                    )
                    count += 1
        return count

    def facts(self, identifier: str = "", kind: str | None = None) -> list[dict]:
        query = (
            "SELECT e.*, c.last_seen FROM current c JOIN evidence e ON c.evidence_id=e.id WHERE 1=1"
        )
        args = []
        if identifier:
            query += " AND (instr(lower(e.subject),lower(?))>0 OR instr(lower(e.value),lower(?))>0)"
            args.extend([identifier, identifier])
        if kind:
            query += " AND e.kind=?"
            args.append(kind)
        return [
            self._decode(r)
            for r in self.connection.execute(query + " ORDER BY e.subject,e.field,e.source", args)
        ]

    @staticmethod
    def _decode(row):
        result = dict(row)
        result["value"] = json.loads(result["value"])
        return result

    def entities(self, kind: str | None = None, identifier: str = "") -> list[dict]:
        grouped = {}
        for fact in self.facts(kind=kind):
            subject = self.canonical(fact["subject"])
            entry = grouped.setdefault(
                subject,
                {
                    "id": subject,
                    "kind": fact["kind"],
                    "fields": {},
                    "evidence": [],
                    "conflicts": [],
                },
            )
            values = entry["fields"].setdefault(fact["field"], [])
            if fact["value"] not in values:
                values.append(fact["value"])
            entry["evidence"].append(
                {
                    k: fact[k]
                    for k in ("id", "field", "source", "external_ref", "last_seen", "confidence")
                }
            )
        for entry in grouped.values():
            entry["conflicts"] = [k for k, v in entry["fields"].items() if len(v) > 1]
            entry["state"] = "CONFLICT" if entry["conflicts"] else "KNOWN"
        return [
            v
            for k, v in grouped.items()
            if not identifier
            or identifier.casefold() in json.dumps(v, ensure_ascii=False).casefold()
        ]

    def evidence(self, identifier: str):
        subjects = {e["id"] for e in self.entities(identifier=identifier)}
        rows = self.connection.execute(
            "SELECT e.*,s.content FROM evidence e JOIN snapshots s ON e.snapshot_id=s.id ORDER BY e.id DESC"
        )
        result = []
        for row in rows:
            if (
                self.canonical(row["subject"]) in subjects
                or identifier.casefold() in row["subject"].casefold()
            ):
                item = self._decode(row)
                item["snapshot"] = json.loads(item.pop("content"))
                result.append(item)
        return result

    def changes(self, acknowledge: bool = False, limit: int = 100):
        rows = self.connection.execute(
            "SELECT c.*,a.value AS old_value,b.value AS new_value FROM changes c LEFT JOIN evidence a ON a.id=c.old_evidence JOIN evidence b ON b.id=c.new_evidence WHERE acknowledged=0 ORDER BY c.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        result = [dict(r) for r in rows]
        for r in result:
            r["old_value"] = json.loads(r["old_value"]) if r["old_value"] else None
            r["new_value"] = json.loads(r["new_value"])
        if acknowledge:
            with self.transaction():
                self.connection.executemany(
                    "UPDATE changes SET acknowledged=1 WHERE id=?", [(r["id"],) for r in result]
                )
        return result

    def change_count(self) -> int:
        return self.connection.execute(
            "SELECT COUNT(*) FROM changes WHERE acknowledged=0"
        ).fetchone()[0]

    def health(self, result: ProviderResult | None = None):
        if result:
            with self.transaction():
                self.connection.execute(
                    "INSERT INTO provider_health VALUES (?,?,?,?,?,?) ON CONFLICT(provider) DO UPDATE SET state=excluded.state,authenticated=excluded.authenticated,message=excluded.message,checked_at=excluded.checked_at,last_success=COALESCE(excluded.last_success,provider_health.last_success)",
                    (
                        result.provider,
                        result.state.value,
                        result.authenticated,
                        clean(result.message),
                        result.checked_at,
                        result.checked_at if result.state.value == "HEALTHY" else None,
                    ),
                )
        rows = [
            dict(r)
            for r in self.connection.execute("SELECT * FROM provider_health ORDER BY provider")
        ]
        observations = {
            r["source"]: r["last_data_sync"]
            for r in self.connection.execute(
                "SELECT source,MAX(last_seen) AS last_data_sync FROM current GROUP BY source"
            )
        }
        for row in rows:
            row["last_data_sync"] = observations.get(row["provider"])
        return rows

    def canonical(self, subject: str) -> str:
        visited = set()
        while subject not in visited:
            visited.add(subject)
            row = self.connection.execute(
                "SELECT canonical FROM mappings WHERE alias=? AND confirmed=1", (subject,)
            ).fetchone()
            if not row:
                return subject
            subject = row[0]
        raise CampusError("Course mapping cycle detected")

    def map(self, alias: str, canonical: str, confidence: float, reason: str, confirmed=True):
        if alias == canonical or self.canonical(canonical) == alias:
            raise CampusError("Course mapping would create a cycle")
        with self.transaction():
            self.connection.execute(
                "INSERT OR REPLACE INTO mappings VALUES (?,?,?,?,?,?)",
                (alias, canonical, confidence, reason, confirmed, now()),
            )
        self.ingest(
            [
                Fact(
                    subject=alias,
                    kind="mapping",
                    field="mapping",
                    value={
                        "canonical": canonical,
                        "confidence": confidence,
                        "confirmed": confirmed,
                    },
                    source="local",
                    external_ref="local:mappings",
                    excerpt=reason,
                )
            ]
        )


def single(entity: dict, field: str, default=None):
    values = entity["fields"].get(field, [])
    return values[0] if len(values) == 1 else default
