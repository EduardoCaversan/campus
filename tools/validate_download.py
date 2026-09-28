"""Download attachments for one known assignment; report counts only."""

import json
from pathlib import Path
from urllib.parse import urlsplit

from campus.config import load_config
from campus.providers.downloads import download_moodle
from campus.store import Store

config = load_config(home=Path.cwd() / ".campus")
store = Store(config.db)
try:
    candidate = next(
        (
            f
            for f in store.facts(kind="assignment")
            if f["field"] == "attachments"
            and any(urlsplit(str(u)).path.lower().endswith(".pdf") for u in f["value"])
        ),
        None,
    )
    if candidate:
        result = download_moodle(config, store, candidate["subject"])
        print(
            json.dumps(
                {
                    "state": result["state"],
                    "files": len(result.get("attachments", [])),
                    "outcomes": [
                        {
                            "state": a["state"],
                            "text_extracted": a.get("text_extracted"),
                            "reason": a.get("reason"),
                        }
                        for a in result.get("attachments", [])
                    ],
                }
            )
        )
    else:
        print(json.dumps({"state": "UNKNOWN", "message": "No known PDF attachment candidate"}))
finally:
    store.close()
