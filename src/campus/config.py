import os
import tomllib
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

from campus.models import CampusError
from campus.security import private_dir


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    home: Path = Field(
        default_factory=lambda: Path(os.getenv("CAMPUS_HOME", str(Path.home() / ".campus")))
    )
    project_dirs: list[Path] = Field(default_factory=list)
    timezone: str = "America/Sao_Paulo"
    stale_hours: int = Field(default=24, ge=1)
    sync_interval_minutes: int = Field(default=15, ge=0)
    portal_url: str = "https://sistemas2.utfpr.edu.br/portal-aluno"
    portal_campus: str | None = None
    moodle_url: str = "https://moodle.utfpr.edu.br"
    mail_mode: str = "browser"
    mail_days: int = Field(default=30, ge=1, le=365)
    max_items: int = Field(default=100, ge=1, le=1000)
    browser_channel: str | None = None
    llm_provider: str = "none"
    llm_model: str = ""
    llm_url: str = "http://localhost:11434"
    log_level: str = "info"

    @field_validator("timezone")
    @classmethod
    def validate_zone(cls, value):
        ZoneInfo(value)
        return value

    @field_validator("portal_url", "moodle_url")
    @classmethod
    def validate_service(cls, value):
        from urllib.parse import urlsplit

        p = urlsplit(value)
        if (
            p.scheme != "https"
            or not p.hostname
            or not (p.hostname == "utfpr.edu.br" or p.hostname.endswith(".utfpr.edu.br"))
            or p.username
            or p.password
        ):
            raise ValueError("University providers require an HTTPS UTFPR hostname")
        return value.rstrip("/")

    @field_validator("mail_mode")
    @classmethod
    def validate_mail(cls, value):
        if value not in {"browser", "imap"}:
            raise ValueError("mail_mode must be browser or imap")
        return value

    @property
    def db(self):
        return self.home / "campus.sqlite3"

    @property
    def artifacts(self):
        return self.home / "artifacts"

    @property
    def reports(self):
        return self.home / "reports"

    def initialize(self):
        private_dir(self.home)
        for folder in ("auth", "artifacts", "reports", "debug", "logs", "downloads"):
            private_dir(self.home / folder)


def load_config(home: Path | None = None, path: Path | None = None) -> Config:
    from dotenv import load_dotenv

    # Explicit cwd only: never crawl parents or expand references in secret values.
    load_dotenv(Path.cwd() / ".env", override=False, interpolate=False, verbose=False)
    selected_home = (
        (home or Path(os.getenv("CAMPUS_HOME", str(Path.home() / ".campus"))))
        .expanduser()
        .resolve()
    )
    path = path or selected_home / "config.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        data["home"] = selected_home
        if os.getenv("CAMPUS_LLM_URL"):
            data["llm_url"] = os.environ["CAMPUS_LLM_URL"]
        config = Config.model_validate(data)
        config.project_dirs = [p.expanduser().resolve() for p in config.project_dirs]
        return config
    except Exception:
        raise CampusError(
            "Invalid configuration; check TOML keys, paths, timezone and HTTPS UTFPR URLs. Values suppressed for privacy."
        ) from None
