"""Inspect the already-discovered enrollment timetable structure only."""

import json
from pathlib import Path

from bs4 import BeautifulSoup

from campus.config import load_config
from campus.providers.browser import browser
from campus.providers.portal_parsing import academic_links, decode_html, rows, text

config = load_config(home=Path.cwd() / ".campus")
with browser(config, "portal") as ctx:
    page = ctx.new_page()
    page.goto(config.portal_url, wait_until="domcontentloaded")
    page.locator(".card-content").first.wait_for(state="attached")
    link = academic_links(page.content(), page.url)["disciplinas matriculadas"]
    response = ctx.request.get(link, max_redirects=0)
    soup = BeautifulSoup(
        decode_html(response.body(), response.headers.get("content-type", "")), "html.parser"
    )
    for table in soup.select("table"):
        direct = list(rows(table))
        if any("Segunda" in " ".join(text(r)) and "Tér" in " ".join(text(r)) for r in direct):
            populated = [r for r in direct[1:] if any(c.get_text(" ", strip=True) for c in r[3:])]
            print(
                json.dumps(
                    {
                        "row_count": len(direct),
                        "structure": [
                            [
                                {
                                    "text": c.get_text(" ", strip=True),
                                    "colspan": c.get("colspan"),
                                    "rowspan": c.get("rowspan"),
                                }
                                for c in r
                            ]
                            for r in populated[:2]
                        ],
                    },
                    ensure_ascii=True,
                )
            )
