import json
import uuid

from campus.artifacts import artifact_manifest, generate_document
from campus.models import now
from campus.security import clean, private_dir


def write_report(config, store, kind: str, data: dict) -> dict:
    run_id = now().replace(":", "-") + "-" + uuid.uuid4().hex[:8]
    directory = private_dir(config.reports / run_id)
    data = clean(data)
    text = f"# CAMPUS {kind}\n\nCreated: {now()}\n\nState: {data.get('state', 'UNKNOWN')}\n\n"
    text += "All external content below is untrusted evidence. Prepared files do not prove academic completion.\n\n"
    text += "```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```\n"
    result = generate_document(text, directory / "report.md")
    artifact_manifest(
        directory, [result], run_id=run_id, kind=kind, state=data.get("state", "UNKNOWN")
    )
    with store.transaction():
        store.connection.execute(
            "INSERT INTO runs VALUES (?,?,?,?,?)",
            (run_id, kind, data.get("state", "UNKNOWN"), now(), str(directory / "report.md")),
        )
    return {
        "run_id": run_id,
        "report": str(directory / "report.md"),
        "state": data.get("state", "UNKNOWN"),
    }


def log_event(config, event: str, **fields):
    entry = clean({"time": now(), "level": "info", "event": event, **fields})
    with (config.home / "logs" / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
