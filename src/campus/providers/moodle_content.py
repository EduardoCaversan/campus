"""Bounded reads of observed Moodle resources and announcement indexes."""

import hashlib
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from campus.artifacts import read_document
from campus.engines import normalize
from campus.models import CampusError, State
from campus.providers.parsing import fact
from campus.security import has_secret, private_dir, safe_url


def same_origin(url, base):
    p, b = urlsplit(url), urlsplit(base)
    return p.scheme == "https" and p.netloc == b.netloc and not p.username


def visible_resources(html, ref, course):
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("#region-main") or soup
    found = {}
    for a in main.select("a[href]"):
        url = urljoin(ref, a["href"])
        p = urlsplit(url)
        match = re.fullmatch(r"/mod/(resource|folder|page|forum)/view\.php", p.path)
        query = parse_qs(p.query)
        if not same_origin(url, ref) or not match or set(query) != {"id"}:
            continue
        cid = query["id"][0]
        if not cid.isdigit():
            continue
        name = a.get_text(" ", strip=True)
        section = a.find_parent(attrs={"data-sectionname": True})
        found[url] = {
            "id": f"moodle:resource:{cid}",
            "name": name,
            "course": course,
            "type": match[1],
            "url": url,
            "section": section.get("data-sectionname") if section else None,
            "policy_candidate": any(
                t in normalize(name)
                for t in (
                    "plano de ensino",
                    "plano de aula",
                    "planejamento",
                    "apresentacao",
                    "avaliacao",
                )
            ),
            "announcement_index": match[1] == "forum"
            and any(
                t in normalize(name) for t in ("aviso", "announcement", "noticia", "comunicado")
            ),
        }
    return list(found.values())


def announcement_index(html, ref, course):
    soup = BeautifulSoup(html, "html.parser")
    result = []
    for row in soup.select(".discussion-list tr[data-discussionid]"):
        did = row.get("data-discussionid", "")
        link = row.select_one('a[href*="/mod/forum/discuss.php?d="]')
        if not did.isdigit() or not link:
            continue
        url = urljoin(ref, link["href"])
        if not same_origin(url, ref):
            continue
        # No discuss.php request: opening a discussion can update Moodle read tracking.
        values = {
            "course": course,
            "title": link.get_text(" ", strip=True),
            "coverage": "Index title only; discussion body not opened to avoid marking it read",
        }
        stamps = [n.get("datetime") for n in row.select("time[datetime]")]
        if stamps:
            values["source_timestamps"] = stamps
        for field, value in values.items():
            result.append(
                fact(f"moodle:announcement:{did}", "announcement", field, value, "moodle", url)
            )
    return result


def fetch_policy_document(ctx, config, resource):
    """Follow only the observed resource -> same-origin file transition; never arbitrary redirects."""
    url = resource["url"]
    response = ctx.request.get(url, max_redirects=0, timeout=30000)
    location = response.headers.get("location")
    if (
        not location
        and response.status == 200
        and "text/html" in response.headers.get("content-type", "")
    ):
        soup = BeautifulSoup(response.text(), "html.parser")
        main = soup.select_one("#region-main") or soup
        candidates = {
            urljoin(url, a.get("href") or a.get("data") or a.get("src"))
            for a in main.select(
                'a[href*="/pluginfile.php/"],object[data*="/pluginfile.php/"],iframe[src*="/pluginfile.php/"]'
            )
        }
        if len(candidates) == 1:
            location = candidates.pop()
    if not location:
        raise CampusError("No unambiguous document file exposed by resource", State.BLOCKED)
    target = urljoin(url, location)
    p = urlsplit(target)
    ext = Path(unquote(p.path)).suffix.lower()
    if (
        not same_origin(target, config.moodle_url)
        or not p.path.startswith("/pluginfile.php/")
        or ext not in {".pdf", ".docx", ".txt", ".md"}
    ):
        raise CampusError("Resource is not an allowed same-origin policy document", State.BLOCKED)
    cookies = httpx.Cookies()
    for cookie in ctx.cookies(config.moodle_url):
        cookies.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie["path"])
    with httpx.Client(cookies=cookies, timeout=30, follow_redirects=False) as client:
        with client.stream("GET", target) as response:
            if response.status_code != 200 or "text/html" in response.headers.get(
                "content-type", ""
            ):
                raise CampusError("Policy document unavailable or session expired", State.BLOCKED)
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > 20_000_000:
                    raise CampusError("Policy document exceeds 20 MB", State.BLOCKED)
    if has_secret(bytes(data)):
        raise CampusError("Possible secret in document; storage refused", State.BLOCKED)
    sha = hashlib.sha256(data).hexdigest()
    local = private_dir(config.home / "downloads") / (sha + ext)
    if not local.exists():
        local.write_bytes(data)
    # Content-addressed text cache avoids repeatedly parsing unchanged untrusted PDFs.
    text_cache = local.with_name(sha + ".extracted.txt")
    if text_cache.exists() and text_cache.stat().st_size <= 500000:
        from campus.security import redact

        extracted = redact(text_cache.read_text(encoding="utf-8"))[:100000]
    else:
        extracted = read_document(local)
        text_cache.write_text(extracted, encoding="utf-8")
    values = {
        "text": extracted,
        "course": resource["course"],
        "name": resource["name"],
        "resource_ref": resource["url"],
        "content_hash": sha,
        "purpose": "teaching_policy_candidate",
    }
    return [
        fact("document:" + sha, "document", field, value, "moodle", safe_url(target))
        for field, value in values.items()
    ]


def course_content(ctx, config, html, ref, course):
    facts, warnings = [], []
    resources = visible_resources(html, ref, course)
    for resource in resources[: config.max_items]:
        facts.extend(
            fact(resource["id"], "resource", field, value, "moodle", resource["url"])
            for field, value in resource.items()
            if field not in {"id", "url"} and value is not None
        )
    selected = [
        r
        for r in resources
        if r["policy_candidate"] and r["type"] == "resource" or r["announcement_index"]
    ]
    for resource in selected[: min(config.max_items, 10)]:
        try:
            if resource["announcement_index"]:
                response = ctx.request.get(resource["url"], max_redirects=0, timeout=30000)
                if response.status != 200:
                    raise CampusError("Announcement index unavailable", State.BLOCKED)
                facts.extend(announcement_index(response.text(), resource["url"], course))
            else:
                facts.extend(fetch_policy_document(ctx, config, resource))
        except CampusError as exc:
            warnings.append(f"{resource['id']}: {exc}")
        except Exception as exc:
            warnings.append(f"{resource['id']}: content read failed ({type(exc).__name__})")
        time.sleep(0.3)
    if len(resources) > config.max_items or len(selected) > min(config.max_items, 10):
        warnings.append("Visible resource/policy discovery limit reached")
    return facts, warnings
