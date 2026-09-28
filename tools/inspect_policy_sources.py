"""Inspect known academic views only; omit identity tables and authentication data."""

import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from campus.config import load_config
from campus.engines import normalize
from campus.providers.browser import authenticated, browser, portal_landing
from campus.providers.portal_parsing import academic_links, decode_html, rows, text
from campus.security import redact
from campus.store import Store

parser = argparse.ArgumentParser()
parser.add_argument("provider", choices=["portal", "moodle"])
parser.add_argument("--resources", action="store_true")
args = parser.parse_args()
config = load_config(home=Path.cwd() / ".campus")
store = Store(config.db)
try:
    with browser(config, args.provider) as ctx:
        page = ctx.new_page()
        page.goto(
            portal_landing(config)
            if args.provider == "portal"
            else config.moodle_url + "/my/courses.php",
            wait_until="domcontentloaded",
        )
        if not authenticated(page, args.provider):
            raise SystemExit("BLOCKED: existing session expired; authenticate normally")
        if args.provider == "portal":
            page.locator(".card-content").first.wait_for(timeout=15000)
            for label, url in academic_links(page.content(), page.url).items():
                response = ctx.request.get(url, max_redirects=0)
                if response.status != 200:
                    print(json.dumps({"view": label, "state": "BLOCKED"}))
                    continue
                soup = BeautifulSoup(
                    decode_html(response.body(), response.headers.get("content-type", "")),
                    "html.parser",
                )
                snippets = []
                for table in soup.select("table"):
                    for cells in rows(table):
                        if any(c.find("table") for c in cells):
                            continue
                        values = text(cells)
                        joined = " | ".join(values)
                        normalized = normalize(joined)
                        if re.search(
                            r"\b(equivalencia|equivalente|optativas|obrigatorias|integralizacao|horas cursadas|carga horaria total|carga horaria cumprida|atividades complementares|observacoes|legenda|limite de faltas|coeficiente|requisitos|aprovacao)\b",
                            normalized,
                        ):
                            if not re.search(
                                r"\b(nome do aluno|registro academico|filiacao|nascimento|cpf|rg)\b",
                                normalized,
                            ):
                                snippets.append(redact(joined)[:1800])
                print(
                    json.dumps(
                        {"view": label, "rule_rows": list(dict.fromkeys(snippets))[:40]},
                        ensure_ascii=True,
                    )
                )
                if args.resources and label == "historico completo":
                    for table in soup.select("table"):
                        direct = [
                            text(c) for c in rows(table) if not any(n.find("table") for n in c)
                        ]
                        if any(
                            any(
                                normalize(v)
                                in {
                                    "cht disciplinas obrigatorias",
                                    "grupo",
                                    "disciplina equivalente",
                                    "cht prevista",
                                    "cht exigida",
                                    "optativas",
                                    "chext disciplinas obrigatorias",
                                }
                                for v in row
                            )
                            for row in direct
                        ):
                            print(
                                json.dumps(
                                    {"history_requirement_table": direct[:18]}, ensure_ascii=True
                                )
                            )
                time.sleep(0.4)
        else:
            refs = sorted(
                {f["external_ref"] for f in store.facts(kind="course") if f["source"] == "moodle"}
            )
            for url in refs:
                response = ctx.request.get(url, max_redirects=0)
                if response.status != 200:
                    continue
                soup = BeautifulSoup(response.text(), "html.parser")
                main = soup.select_one("#region-main") or soup
                links = []
                for a in main.select("a[href]"):
                    target = urljoin(url, a["href"])
                    if urlsplit(target).netloc != urlsplit(config.moodle_url).netloc:
                        continue
                    if any(
                        s in urlsplit(target).path
                        for s in (
                            "/mod/resource/view.php",
                            "/mod/folder/view.php",
                            "/mod/forum/view.php",
                            "/mod/page/view.php",
                            "/pluginfile.php/",
                        )
                    ):
                        links.append({"label": redact(a.get_text(" ", strip=True)), "url": target})
                print(
                    json.dumps({"course_ref": url, "visible_links": links[:80]}, ensure_ascii=True)
                )
                if args.resources:
                    for link in links:
                        label = normalize(link["label"])
                        if not any(
                            t in label
                            for t in (
                                "planejamento",
                                "plano de",
                                "apresentacao da disciplina",
                                "avisos",
                            )
                        ):
                            continue
                        response = ctx.request.get(link["url"], max_redirects=0)
                        detail = {
                            "label": link["label"],
                            "status": response.status,
                            "type": response.headers.get("content-type"),
                            "redirect": response.headers.get("location"),
                        }
                        if "text/html" in response.headers.get("content-type", ""):
                            content = BeautifulSoup(response.text(), "html.parser")
                            main = content.select_one("#region-main") or content
                            detail["embedded"] = [
                                n.get("src") or n.get("data")
                                for n in main.select("iframe[src],object[data],embed[src]")
                            ]
                            detail["file_links"] = [
                                a["href"] for a in main.select('a[href*="/pluginfile.php/"]')
                            ]
                            detail["structure"] = [
                                {
                                    "tag": n.name,
                                    "class": n.get("class"),
                                    "attributes": sorted(n.attrs),
                                }
                                for n in main.select("table,article,.forumpost,.discussion")
                            ][:12]
                            if "/forum/" in link["url"]:
                                detail["headers"] = [
                                    n.get_text(" ", strip=True) for n in main.select("th")
                                ]
                                detail["posts"] = [
                                    redact(n.get_text(" ", strip=True))[:1600]
                                    for n in main.select(".posting,.post-content")
                                ][:3]
                        print(json.dumps(detail, ensure_ascii=True))
                        time.sleep(0.4)
                time.sleep(0.4)
finally:
    store.close()
