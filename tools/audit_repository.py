"""Check publishable files against loaded secrets; output names/counts, never values."""

import argparse
import json
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

from campus.security import SECRET_NAMES

parser = argparse.ArgumentParser()
parser.add_argument(
    "--runtime",
    action="store_true",
    help="Also scan private text reports/logs for loaded credentials; output counts only",
)
args = parser.parse_args()

load_dotenv(Path.cwd() / ".env", override=False, interpolate=False)
result = subprocess.run(
    ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
    capture_output=True,
    check=True,
)
files = sorted(set(n.decode("utf-8") for n in result.stdout.split(b"\0") if n))
secrets = [os.environ[k].encode() for k in SECRET_NAMES if os.getenv(k)]
violations = []
staged_checked = 0
for name in files:
    path = Path(name)
    if (
        any(
            part in {".campus", ".venv", "auth", "credentials", "reports", "artifacts"}
            for part in path.parts
        )
        or path.name == ".env"
        or path.suffix.lower() in {".sqlite", ".sqlite3", ".db", ".har"}
        or path.name.lower().endswith(("cookies.json", "storage-state.json", "trace.zip"))
    ):
        violations.append({"file": name, "reason": "private file eligible for tracking"})
        continue
    if path.is_file() and any(secret in path.read_bytes() for secret in secrets):
        violations.append({"file": name, "reason": "loaded credential detected"})
    staged = subprocess.run(["git", "show", ":" + name], capture_output=True)
    if staged.returncode == 0:
        staged_checked += 1
        if any(secret in staged.stdout for secret in secrets):
            violations.append({"file": name, "reason": "loaded credential in actual index blob"})
runtime_checked = runtime_violations = 0
if args.runtime:
    for directory in (Path(".campus/logs"), Path(".campus/reports"), Path(".campus/artifacts")):
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".json", ".jsonl", ".md", ".txt"}:
                runtime_checked += 1
                runtime_violations += any(secret in path.read_bytes() for secret in secrets)
    if runtime_violations:
        violations.append(
            {"reason": "loaded credential in private report/log text", "count": runtime_violations}
        )
print(
    json.dumps(
        {
            "state": "FAILED" if violations else "PASSED",
            "files_checked": len(files),
            "index_blobs_checked": staged_checked,
            "runtime_text_files_checked": runtime_checked,
            "violations": violations,
        }
    )
)
raise SystemExit(1 if violations else 0)
