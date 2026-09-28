import hashlib
import json
import os
import re
from enum import StrEnum
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from campus.models import CampusError, State

SECRET_NAMES = (
    "UTFPR_USERNAME",
    "UTFPR_PASSWORD",
    "MOODLE_USERNAME",
    "MOODLE_PASSWORD",
    "MOODLE_TOKEN",
    "CAMPUS_MAIL_APP_PASSWORD",
    "CAMPUS_LLM_API_KEY",
)
SENSITIVE_KEY = re.compile(
    r"password|passwd|senha|secret|token|cookie|authorization|sesskey|csrf|credential|api.?key",
    re.I,
)
SECRET_CONTENT = re.compile(
    r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b|"
    r"(?im:^\s*[\w.-]*(?:password|passwd|senha|secret|token|api[_-]?key)[\w.-]*\s*[:=]\s*[\"']?[^\s\"']{4,})"
)


def redact(text: str) -> str:
    for name in SECRET_NAMES:
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[REDACTED]")
    text = re.sub(
        r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z ]+ )?PRIVATE KEY-----",
        "[REDACTED PRIVATE KEY]",
        text,
    )
    text = SECRET_CONTENT.sub("[REDACTED]", text)
    text = re.sub(r"(?i)(bearer\s+)\S+", r"\1[REDACTED]", text)
    text = re.sub(
        r"(?i)((?:password|passwd|senha|token|sesskey|secret|api_key)\s*[=:]\s*)[^\s&\"'<>]+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(r"https?://[^\s/@]+@", "https://[REDACTED]@", text)
    # Prevent terminal control sequence injection from untrusted source content.
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", "", text)


def clean(value):
    if isinstance(value, dict):
        return {
            str(k): "[REDACTED]" if SENSITIVE_KEY.search(str(k)) else clean(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [clean(v) for v in value]
    return redact(value) if isinstance(value, str) else value


def safe_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return redact(url)
    host = parts.hostname or ""
    if parts.port:
        host += f":{parts.port}"
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not SENSITIVE_KEY.search(k)])
    return urlunsplit((parts.scheme, host, parts.path, query, ""))


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def inside(root: Path, candidate: Path) -> Path:
    root = root.resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise CampusError("Output path must remain inside its configured directory")
    return resolved


def private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)
    return path


class Capability(StrEnum):
    READ_REMOTE = "READ_REMOTE"
    ANALYZE = "ANALYZE"
    GENERATE_LOCAL = "GENERATE_LOCAL"
    EXECUTE_LOCAL = "EXECUTE_LOCAL"
    WRITE_REMOTE = "WRITE_REMOTE"
    SUBMIT = "SUBMIT"
    SEND_EMAIL = "SEND_EMAIL"


REMOTE_WRITES = {Capability.WRITE_REMOTE, Capability.SUBMIT, Capability.SEND_EMAIL}


def authorize(capability: Capability, *, confirmed: bool = False, dry_run: bool = True) -> dict:
    if capability in REMOTE_WRITES:
        if not dry_run:
            raise CampusError(
                "Remote writes are disabled in this release, including confirmed actions",
                State.BLOCKED,
            )
        return {
            "state": State.BLOCKED,
            "dry_run": True,
            "executed": False,
            "requires_confirmation": True,
            "capability": capability.value,
        }
    return {"state": State.COMPLETED, "capability": capability.value}


def has_secret(data: bytes) -> bool:
    text = data.decode("utf-8", errors="ignore")
    return bool(SECRET_CONTENT.search(text)) or any(
        os.environ.get(name) and os.environ[name].encode() in data for name in SECRET_NAMES
    )
