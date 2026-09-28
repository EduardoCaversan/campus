"""Inspect built archives without extraction; print counts only, never secret matches."""

import json
import os
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

from dotenv import load_dotenv

from campus.security import SECRET_NAMES

load_dotenv(Path.cwd() / ".env", override=False, interpolate=False)
secrets = [os.environ[k].encode() for k in SECRET_NAMES if os.getenv(k)]


def check(name, data):
    path = PurePosixPath(name)
    return (
        path.is_absolute()
        or ".." in path.parts
        or any(
            p in {".env", ".campus", ".venv", ".git", "auth", "credentials", "reports", "artifacts"}
            for p in path.parts
        )
        or any(secret in data for secret in secrets)
    )


failed = False
for path in sorted(Path("dist").iterdir()):
    violations, count = 0, 0
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                count += 1
                violations += bool(check(name, archive.read(name)))
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path) as archive:
            for member in archive.getmembers():
                if member.isfile():
                    count += 1
                    violations += bool(check(member.name, archive.extractfile(member).read()))
                elif not member.isdir():
                    violations += 1
    else:
        continue
    failed |= bool(violations)
    print(
        json.dumps(
            {
                "package": path.name,
                "files_checked": count,
                "violations": violations,
                "state": "FAILED" if violations else "PASSED",
            }
        )
    )
raise SystemExit(1 if failed else 0)
