import hashlib
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx

from campus.artifacts import read_document
from campus.models import CampusError, State
from campus.providers.browser import browser
from campus.providers.parsing import fact
from campus.security import has_secret, inside, private_dir, safe_url


def download_moodle(config, store, identifier: str):
    """Download only attachment links already observed in the user's course evidence."""
    facts = store.facts(identifier=identifier, kind="assignment")
    links = sorted({url for f in facts if f["field"] == "attachments" for url in f["value"]})
    if not links:
        return {"state": "UNKNOWN", "message": "No known attachment links for this assignment"}
    host = urlsplit(config.moodle_url).hostname
    root = private_dir(config.home / "downloads")
    results = []
    with browser(config, "moodle") as ctx:
        cookies = httpx.Cookies()
        for cookie in ctx.cookies(config.moodle_url):
            cookies.set(
                cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie["path"]
            )
        with httpx.Client(cookies=cookies, timeout=30, follow_redirects=False) as client:
            for link in links[: config.max_items]:
                parsed = urlsplit(link)
                if (
                    parsed.scheme != "https"
                    or parsed.hostname != host
                    or not parsed.path.startswith("/pluginfile.php/")
                ):
                    results.append(
                        {
                            "state": "BLOCKED",
                            "reason": "Attachment is outside the authenticated Moodle file origin",
                        }
                    )
                    continue
                ext = Path(unquote(parsed.path)).suffix.lower()
                if ext not in {".pdf", ".docx", ".txt", ".md", ".csv", ".zip"}:
                    results.append(
                        {
                            "state": "BLOCKED",
                            "reason": "Unsupported attachment type; executable content is not downloaded",
                        }
                    )
                    continue
                try:
                    # Redirects are not followed: credentials must never be forwarded to another origin.
                    with client.stream("GET", link) as response:
                        if response.status_code != 200 or "text/html" in response.headers.get(
                            "content-type", ""
                        ):
                            raise CampusError(
                                "Attachment unavailable or redirected to login", State.BLOCKED
                            )
                        data = bytearray()
                        for chunk in response.iter_bytes():
                            data.extend(chunk)
                            if len(data) > 20_000_000:
                                raise CampusError("Attachment exceeds 20 MB", State.BLOCKED)
                    if has_secret(bytes(data)):
                        raise CampusError(
                            "Attachment contains a possible secret; storage blocked", State.BLOCKED
                        )
                    sha = hashlib.sha256(data).hexdigest()
                    target = inside(root, root / (sha + ext))
                    if not target.exists():
                        target.write_bytes(data)
                    extracted = None
                    if ext != ".zip":
                        try:
                            extracted = read_document(target)
                        except CampusError:
                            pass
                    if extracted:
                        store.ingest(
                            [
                                fact(
                                    "document:" + sha,
                                    "document",
                                    "text",
                                    extracted,
                                    "moodle",
                                    safe_url(link),
                                )
                            ]
                        )
                    results.append(
                        {
                            "state": "COMPLETED",
                            "path": str(target),
                            "sha256": sha,
                            "text_extracted": extracted is not None,
                            "warning": "Untrusted document; no embedded code executed, archives not extracted",
                        }
                    )
                except CampusError as exc:
                    results.append({"state": exc.state.value, "reason": str(exc)})
                except Exception as exc:
                    results.append(
                        {
                            "state": "FAILED",
                            "reason": f"Attachment operation failed ({type(exc).__name__}); details suppressed",
                        }
                    )
    return {
        "state": "COMPLETED"
        if len(links) <= config.max_items and all(r["state"] == "COMPLETED" for r in results)
        else "PARTIAL",
        "limited": len(links) > config.max_items,
        "attachments": results,
    }
