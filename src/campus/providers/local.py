import os
import subprocess
from pathlib import Path

from campus.models import CampusError, ProviderResult, State
from campus.providers.parsing import fact
from campus.security import digest, redact

EXCLUDED = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "build",
    "dist",
    ".campus",
    "__pycache__",
    ".idea",
    "target",
}


def git(path: Path, *args) -> str:
    allowed = {"status", "log", "diff", "branch", "remote", "rev-parse", "ls-files"}
    if not args or args[0] not in allowed:
        raise CampusError("Git operation is not in the read-only allowlist")
    env = {
        **os.environ,
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    result = subprocess.run(
        [
            "git",
            "--no-pager",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=",
            "-c",
            "diff.external=",
            "-C",
            str(path),
            *args,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        env=env,
        shell=False,
    )
    if result.returncode:
        raise CampusError(
            "Read-only Git inspection failed; repository may be uninitialized or inaccessible"
        )
    if args[0] == "ls-files" and "-z" in args:
        return result.stdout  # NUL separators are protocol data, not terminal text.
    return redact(result.stdout.strip())


class GitProvider:
    name = "git"

    def __init__(self, config):
        self.config = config

    def check(self):
        return ProviderResult(
            provider=self.name,
            state=State.HEALTHY if self.config.project_dirs else State.UNKNOWN,
            message="Project roots configured"
            if self.config.project_dirs
            else "No project_dirs configured",
        )

    def sync(self):
        facts, warnings, found = [], [], set()
        for root in self.config.project_dirs:
            if not root.is_dir():
                warnings.append("A configured project root is unavailable")
                continue
            for current, directories, _ in os.walk(root, followlinks=False):
                path = Path(current)
                directories[:] = sorted(
                    d
                    for d in directories
                    if d not in EXCLUDED
                    and not (path / d).is_symlink()
                    and not (path / d).is_junction()
                )
                if len(path.relative_to(root).parts) >= 4:
                    directories[:] = []
                if (path / ".git").exists():
                    found.add(path.resolve())
                if len(found) >= self.config.max_items:
                    warnings.append("Repository discovery limit reached")
                    break
        for path in sorted(found):
            subject = "git:repo:" + digest(str(path))[:16]
            ref = "local-repository:" + digest(str(path))
            values = {"name": path.name, "path": str(path)}
            try:
                values.update(
                    {
                        "commit": git(path, "rev-parse", "HEAD"),
                        "status": git(path, "status", "--porcelain=v1"),
                        "branches": git(path, "branch", "--format=%(refname:short)"),
                        "recent_commits": git(path, "log", "-5", "--format=%h %s"),
                        "remotes": git(path, "remote", "-v"),
                    }
                )
                for name in ("README.md", "README.txt", "readme.md"):
                    file = path / name
                    if file.is_file() and not file.is_symlink() and file.stat().st_size < 200000:
                        values["readme"] = redact(
                            file.read_text(encoding="utf-8", errors="replace")
                        )
                        break
            except CampusError:
                warnings.append("A repository could not be fully inspected")
            for field, value in values.items():
                facts.append(fact(subject, "repository", field, value, self.name, ref))
        return ProviderResult(
            provider=self.name,
            state=State.PARTIAL
            if warnings
            else State.HEALTHY
            if self.config.project_dirs
            else State.UNKNOWN,
            facts=facts,
            warnings=warnings,
            message=f"Discovered {len(found)} repositories; no files modified",
        )


class GitHubProvider:
    name = "github"

    def __init__(self, config):
        self.config = config

    def check(self):
        import shutil

        if not shutil.which("gh"):
            return ProviderResult(
                provider=self.name,
                state=State.BLOCKED,
                message="Optional GitHub CLI is not installed",
            )
        result = subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=20)
        return ProviderResult(
            provider=self.name,
            state=State.HEALTHY if result.returncode == 0 else State.BLOCKED,
            authenticated=result.returncode == 0,
            message="GitHub CLI authentication checked; credential output suppressed",
        )

    def sync(self):
        import json

        health = self.check()
        if not health.authenticated:
            return health
        result = subprocess.run(
            [
                "gh",
                "repo",
                "list",
                "--limit",
                str(self.config.max_items),
                "--json",
                "name,url,description,updatedAt,isPrivate",
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode:
            return ProviderResult(
                provider=self.name,
                state=State.FAILED,
                message="GitHub read-only repository list failed",
            )
        data = json.loads(result.stdout)
        return ProviderResult(
            provider=self.name,
            state=State.PARTIAL,
            authenticated=True,
            facts=[
                fact(
                    "github:" + digest(r["url"])[:20],
                    "repository",
                    "remote_details",
                    r,
                    self.name,
                    r["url"],
                )
                for r in data
            ],
            message="Read authenticated user's repository metadata",
            warnings=[
                "GitHub listing is bounded; no code cloned, issues changed or remote writes performed"
            ],
        )
