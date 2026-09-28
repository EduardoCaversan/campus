"""Exercise application services against real sessions; print only operational summaries."""

import argparse
import json
from pathlib import Path

from campus.config import load_config
from campus.service import Campus

parser = argparse.ArgumentParser()
parser.add_argument("provider", choices=["portal", "moodle", "mail", "git", "github", "doctor"])
args = parser.parse_args()
campus = Campus(load_config(home=Path.cwd() / ".campus"))
try:
    if args.provider == "doctor":
        result = campus.doctor()
        print(
            json.dumps(
                {
                    "state": result["state"],
                    "database": result["database"],
                    "providers": [
                        {
                            "provider": r["provider"],
                            "state": r["state"],
                            "authenticated": r["authenticated"],
                            "message": r["message"],
                        }
                        for r in result["providers"]
                    ],
                }
            )
        )
    else:
        result = campus.sync(args.provider, force=True)
        print(
            json.dumps(
                {
                    "state": result["state"],
                    "providers": result["providers"],
                    "changes": result["changes"],
                    "entity_counts": {
                        kind: len(campus.store.entities(kind))
                        for kind in ("course", "assignment", "document", "mail")
                    },
                },
                default=str,
            )
        )
finally:
    campus.store.close()
