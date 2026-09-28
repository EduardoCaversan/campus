"""Inspect Gmail list DOM shape, never message text or account identifiers."""

import json
from pathlib import Path
from urllib.parse import quote, urlsplit

from campus.config import load_config
from campus.providers.browser import authenticated, browser

config = load_config(home=Path.cwd() / ".campus")
with browser(config, "mail") as ctx:
    page = ctx.new_page()
    failed = set()
    page.on(
        "requestfailed", lambda request: failed.add((request.method, urlsplit(request.url).path))
    )
    query = f"newer_than:{config.mail_days}d {{from:(utfpr.edu.br) subject:(UTFPR Moodle)}}"
    page.goto(
        "https://mail.google.com/mail/u/0/#search/" + quote(query, safe=""),
        wait_until="domcontentloaded",
    )
    page.wait_for_timeout(5000)
    rows = page.locator('[role="main"] tr.zA')
    print(
        json.dumps(
            {
                "authenticated_institutional": authenticated(page, "mail"),
                "row_count": rows.count(),
                "thread_nodes": page.locator("[data-thread-id], [data-legacy-thread-id]").count(),
                "row_attribute_names": rows.first.evaluate(
                    "e => ({row:[...e.attributes].map(a=>a.name), children:[...e.querySelectorAll('*')].flatMap(n=>[...n.attributes].map(a=>a.name)).filter((v,i,a)=>a.indexOf(v)===i)})"
                )
                if rows.count()
                else None,
                "blocked_requests": sorted(failed),
            },
            ensure_ascii=True,
        )
    )
