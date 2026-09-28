"""Inspect table structure, not student marks, in a few known submitted assignment views."""

import json
import time
from pathlib import Path

from bs4 import BeautifulSoup

from campus.config import load_config
from campus.providers.browser import browser
from campus.store import Store, single

config = load_config(home=Path.cwd() / ".campus")
store = Store(config.db)
try:
    candidates = [
        e for e in store.entities("assignment") if single(e, "submission_state") == "submitted"
    ]
    with browser(config, "moodle") as ctx:
        for entry in candidates[:3]:
            url = next(ev["external_ref"] for ev in entry["evidence"] if ev["source"] == "moodle")
            response = ctx.request.get(url, max_redirects=0)
            soup = BeautifulSoup(response.text(), "html.parser")
            main = soup.select_one("#region-main")
            print(
                json.dumps(
                    {
                        "status": response.status,
                        "tables": [
                            {
                                "classes": table.get("class"),
                                "parent_classes": table.parent.get("class"),
                                "headers": [
                                    cell.get_text(" ", strip=True) for cell in table.select("th")
                                ],
                            }
                            for table in main.select("table")
                        ]
                        if main
                        else [],
                        "feedback_nodes": [
                            {"tag": n.name, "class": n.get("class")}
                            for n in soup.select('[class*="feedback"]')
                        ][:12],
                    },
                    ensure_ascii=True,
                )
            )
            time.sleep(0.4)
finally:
    store.close()
