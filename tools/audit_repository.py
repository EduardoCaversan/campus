"""Check publishable files against loaded secrets; output names/counts, never values."""
import json
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path.cwd() / ".env", override=False, interpolate=False)
result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], capture_output=True, check=True)
files = sorted(set(n.decode("utf-8") for n in result.stdout.split(b"\0") if n))
secrets = [os.environ[k].encode() for k in ("UTFPR_USERNAME", "UTFPR_PASSWORD", "MOODLE_USERNAME", "MOODLE_PASSWORD", "MOODLE_TOKEN", "CAMPUS_MAIL_APP_PASSWORD") if os.getenv(k)]
violations = []
for name in files:
    path = Path(name)
    if any(part in {".campus", ".venv", "auth", "credentials", "reports", "artifacts"} for part in path.parts) or path.name == ".env":
        violations.append({"file": name, "reason": "private file eligible for tracking"})
        continue
    if path.is_file() and any(secret in path.read_bytes() for secret in secrets):
        violations.append({"file": name, "reason": "loaded credential detected"})
print(json.dumps({"state": "FAILED" if violations else "PASSED", "files_checked": len(files), "violations": violations}))
raise SystemExit(1 if violations else 0)
