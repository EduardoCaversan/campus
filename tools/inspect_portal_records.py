"""Navigate only four explicitly read-only academic menu entries; print parser structure."""

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from campus.config import load_config
from campus.providers.browser import authenticated, browser
from campus.providers.parsing import plain

config = load_config(home=Path.cwd() / ".campus")
with browser(config, "portal") as ctx:
    page = ctx.new_page()
    page.goto(config.portal_url, wait_until="domcontentloaded")
    page.locator(".card").first.wait_for(state="attached", timeout=15000)
    if not authenticated(page, "portal"):
        raise SystemExit("BLOCKED: academic portal session missing")
    for label in (
        "Boletim",
        "Disciplinas Matriculadas",
        "Histórico Completo",
        "Matrizes Curriculares",
    ):
        blocked = set()
        page.on(
            "requestfailed", lambda r, failed=blocked: failed.add((r.method, urlsplit(r.url).path))
        )
        menu = BeautifulSoup(page.content(), "html.parser")
        card = next(
            n
            for n in menu.select(".card-content")
            if n.get_text(" ", strip=True).lower() == label.lower()
        )
        path = re.search(r"\.src\s*=\s*['\"]([^'\"]+)['\"]", card["onclick"]).group(1)
        target = urljoin(page.url, path)
        response = ctx.request.get(target)
        soup = BeautifulSoup(response.body().decode("iso-8859-1"), "html.parser")
        # Inspect only leaf tables; surrounding layout tables can contain identity fields.
        structures = []
        for table in soup.select("table"):
            rows = [r for r in table.select("tr") if r.find_parent("table") is table]
            for i, row in enumerate(rows):
                cells = row.find_all(["th", "td"], recursive=False)
                texts = [c.get_text(" ", strip=True) for c in cells]
                if any(t in ("Código", "Cód.", "Disciplina") for t in texts) and len(cells) >= 8:
                    following = []
                    for r in rows[i + 1 : i + 3]:
                        vals = [
                            c.get_text(" ", strip=True)
                            for c in r.find_all(["th", "td"], recursive=False)
                        ]
                        following.append(vals)
                    structures.append({"headers": texts, "sample_rows": following})
        visible = soup.get_text(" ", strip=True)
        print(
            json.dumps(
                {
                    "view": label,
                    "content_type": response.headers.get("content-type"),
                    "term_labels": re.findall(
                        r".{0,25}(?:Ano/Per|Ano/Sem|Letivo|Matriz:|Matriz\s|Semestre:).{0,75}",
                        visible,
                    )[:8],
                    "selects": [
                        {
                            "name": s.get("name"),
                            "id": s.get("id"),
                            "options": [
                                {
                                    "label": o.get_text(" ", strip=True),
                                    "value": o.get("value"),
                                    "selected": o.has_attr("selected"),
                                }
                                for o in s.select("option")
                            ][:20],
                        }
                        for s in soup.select("select")
                    ],
                    "numeric_rule_notes": [
                        p
                        for p in re.findall(
                            r".{0,35}(?:75%|75 %|limite de faltas|Limite de Faltas|25%|25 %).{0,200}",
                            visible,
                        )
                    ][:6],
                    "grade_table_headers": [
                        [
                            c.get_text(" ", strip=True)
                            for c in r.find_all(["td", "th"], recursive=False)
                        ]
                        for r in soup.select("tr")
                        if r.find_all(["td", "th"], recursive=False)
                        and r.find_all(["td", "th"], recursive=False)[0].get_text(" ", strip=True)
                        == "Data"
                    ],
                },
                ensure_ascii=True,
            )
        )
        headers = []
        for table in soup.select("table"):
            candidates = [
                row
                for row in table.select("tr")
                if any(
                    re.search(
                        r"(?i)disciplina|nota|falta|hor.ria|per.odo|cr.dito|c.digo|requisito",
                        c.get_text(),
                    )
                    for c in row.select("th,td")
                )
            ]
            if candidates:
                headers.append([plain(str(c))[:100] for c in candidates[0].select("th,td")][:20])
        print(
            json.dumps(
                {
                    "menu": label,
                    "path": urlsplit(target).path,
                    "parameter_names": list(parse_qs(urlsplit(target).query)),
                    "tables": len(soup.select("table")),
                    "forms": [
                        {
                            "action": urlsplit(f.get("action", "")).path,
                            "method": f.get("method"),
                            "inputs": [
                                {"name": n.get("name"), "type": n.get("type")}
                                for n in f.select("input")
                            ],
                            "selects": [
                                {
                                    "name": s.get("name"),
                                    "options": [
                                        o.get_text(" ", strip=True) for o in s.select("option")
                                    ][:10],
                                }
                                for s in f.select("select")
                            ],
                        }
                        for f in soup.select("form")
                    ],
                    "blocked": sorted(blocked),
                },
                ensure_ascii=True,
            )
        )
