"""Inspect only deadline/status labels on an owned Moodle assignment."""

import json
from pathlib import Path

from bs4 import BeautifulSoup

from campus.config import load_config
from campus.providers.browser import browser
from campus.providers.parsing import plain
from campus.store import Store

config = load_config(home=Path.cwd() / ".campus")
store = Store(config.db)
references = list(dict.fromkeys(f["external_ref"] for f in store.facts(kind="assignment")))[:3]
store.close()
with browser(config, "moodle") as ctx:
    page = ctx.new_page()
    for ref in references:
        page.goto(ref, wait_until="domcontentloaded")
        soup = BeautifulSoup(page.content(), "html.parser")
        print(
            json.dumps(
                {
                    "date_elements": [
                        plain(str(n))
                        for n in soup.select(
                            '.activity-dates, [data-region="activity-dates"], time'
                        )
                    ],
                    "status_rows": [
                        {
                            "label": plain(str(tr.select_one("th,td"))),
                            "values": [plain(str(td)) for td in tr.select("td")[1:]],
                        }
                        for tr in soup.select(".submissionstatustable tr")
                    ],
                    "activity_attributes": [
                        {k: v for k, v in n.attrs.items() if k.startswith("data-")}
                        for n in soup.select(".activity-dates")
                    ],
                    "intro_attachment_count": len(soup.select('#intro a[href*="pluginfile"]')),
                },
                ensure_ascii=True,
            )
        )
