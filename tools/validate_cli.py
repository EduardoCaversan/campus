"""Run actual CLI commands; summarize outcomes without echoing private records."""

import json
import subprocess
import sys
from pathlib import Path

from campus.artifacts import validate_artifact

base = [sys.executable, "-m", "campus", "--home", str(Path.cwd() / ".campus"), "--json"]
commands = [
    ["status"],
    ["courses"],
    ["deadlines"],
    ["attendance"],
    ["grades"],
    ["plan"],
    ["changes"],
    ["ask", "what do I need to do this week?"],
    ["evidence", "moodle"],
    ["work"],
    ["report", "--pdf"],
]
for command in commands:
    result = subprocess.run([*base, *command], capture_output=True, encoding="utf-8", timeout=60)
    try:
        payload = json.loads(result.stdout)
        summary = {
            "command": command[0],
            "exit_code": result.returncode,
            "valid_json": True,
            "state": payload.get("state") if isinstance(payload, dict) else None,
            "records": len(payload) if isinstance(payload, list) else None,
        }
        if command[0] == "work":
            paths = [Path(a["path"]) for t in payload["tasks"] for a in t["artifacts"]]
            summary.update(
                tasks=len(payload["tasks"]),
                generated=len(paths),
                validated=all(validate_artifact(p) for p in paths),
            )
        if command[0] == "report" and payload.get("pdf"):
            summary["pdf_validated"] = validate_artifact(Path(payload["pdf"]["path"]))
        print(json.dumps(summary))
    except (ValueError, KeyError, TypeError):
        try:
            error = json.loads(result.stderr)
        except ValueError:
            error = {"state": "FAILED", "message": "Non-JSON error output suppressed"}
        print(
            json.dumps(
                {
                    "command": command[0],
                    "exit_code": result.returncode,
                    "valid_json": False,
                    "state": "FAILED",
                    "error": error,
                }
            )
        )
