"""Run actual CLI commands; summarize outcomes without echoing private records."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from campus.artifacts import validate_artifact

parser = argparse.ArgumentParser()
parser.add_argument("--installed", action="store_true")
parser.add_argument(
    "--network", action="store_true", help="Also verify setup and doctor using existing sessions"
)
args = parser.parse_args()
entry = (
    [str(Path(sys.executable).parent / ("campus.exe" if sys.platform == "win32" else "campus"))]
    if args.installed
    else [sys.executable, "-m", "campus"]
)
base = [*entry, "--home", str(Path.cwd() / ".campus"), "--json"]
commands = [
    ["status"],
    ["courses"],
    ["mail"],
    ["repos"],
    ["deadlines"],
    ["attendance"],
    ["attendance", "--day", "friday"],
    ["grades"],
    ["plan"],
    ["analyze-mail"],
    ["analyze-policies"],
    ["grade-policy"],
    ["requirements"],
    ["announcements"],
    ["events"],
    ["changes"],
    ["ask", "what do I need to do this week?"],
    ["ask", "can I miss Friday?"],
    ["evidence", "moodle"],
    ["work"],
    ["report", "--pdf"],
]
if args.network:
    commands = [["setup", "--no-authenticate"], ["doctor"], *commands]
failed = False
for command in commands:
    result = subprocess.run(
        [*base, *command],
        capture_output=True,
        encoding="utf-8",
        timeout=300 if command[0] == "setup" else 90,
    )
    try:
        payload = json.loads(result.stdout)
        summary = {
            "command": " ".join(command),
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
        if command[0] in {"setup", "doctor"}:
            summary["providers"] = [
                {"provider": p["provider"], "state": p["state"]} for p in payload["providers"]
            ]
        failed |= (
            result.returncode not in {0, 2}
            or summary.get("state") == "FAILED"
            or summary.get("validated") is False
            or summary.get("pdf_validated") is False
        )
        print(json.dumps(summary))
    except (ValueError, KeyError, TypeError):
        failed = True
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
raise SystemExit(1 if failed else 0)
