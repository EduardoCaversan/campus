"""Structural portal interoperability inspection; no student records or credentials printed."""

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from campus.config import load_config
from campus.providers.browser import authenticated, browser

config = load_config(home=Path.cwd() / ".campus")
with browser(config, "portal") as ctx:
    page = ctx.new_page()
    requests, failed = set(), set()
    page.on("request", lambda r: requests.add((r.method, urlsplit(r.url).path, r.resource_type)))
    page.on("requestfailed", lambda r: failed.add((r.method, urlsplit(r.url).path)))
    page.goto(config.portal_url, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    soup = BeautifulSoup(page.content(), "html.parser")
    scripts = "\n".join(s.get_text() for s in soup.select("script:not([src])"))
    from campus.security import redact

    print(
        json.dumps(
            {
                "read_card_markup": [
                    redact(str(n))
                    for n in soup.select(".card")
                    if n.get_text(" ", strip=True) == "Boletim"
                ]
            }
        )
    )
    print(
        json.dumps(
            {
                "authenticated": authenticated(page, "portal"),
                "requests": sorted(requests),
                "blocked": sorted(failed),
                "cards": [
                    {
                        "label": n.get_text(" ", strip=True),
                        "quoted_arguments": [
                            s
                            for s in re.findall(r"['\"]([^'\"]+)['\"]", n.get("onclick", ""))
                            if "." in s and not s.startswith("if_")
                        ],
                    }
                    for n in soup.select(".card")
                ],
                "academic_menu": [
                    {
                        "label": n.get_text(" ", strip=True),
                        "path": urlsplit(n.get("href", "")).path,
                        "onclick_function": n.get("onclick", "").split("(")[0],
                    }
                    for n in soup.select("#div_CarregaAjaxMenu a")
                ],
                "script_paths": [
                    urlsplit(s.get("src", "")).path for s in soup.select("script[src]")
                ],
                "procedure_literals": sorted(
                    set(
                        re.findall(
                            r"[\"\']([a-zA-Z0-9_/.-]*(?:mpmenu|mpp|\.php|\.inicio)[a-zA-Z0-9_/.-]*)[\"\']",
                            scripts,
                        )
                    )
                ),
                "fetch_calls": re.findall(r"(?:fetch|\.get|\.post)\([\"\']([^\"\'?]+)", scripts),
                "iframe_attributes": [
                    {k: v for k, v in f.attrs.items() if k in ("id", "name", "src")}
                    for f in soup.select("iframe")
                ],
                "menu_shapes": [
                    {"tag": n.name, "id": n.get("id"), "class": n.get("class")}
                    for n in soup.select("[id]")
                ][:30],
                "onclick_functions": sorted(
                    set(n.get("onclick", "").split("(")[0] for n in soup.select("[onclick]"))
                ),
            },
            ensure_ascii=True,
        )
    )
