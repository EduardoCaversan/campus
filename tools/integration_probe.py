"""Read-only integration diagnostics. Output structural metadata/counts only."""

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from campus.config import load_config
from campus.providers.browser import authenticated, browser

parser = argparse.ArgumentParser()
parser.add_argument("provider", choices=["portal", "moodle"])
parser.add_argument("--login", action="store_true")
parser.add_argument("--inspect", action="store_true")
args = parser.parse_args()
config = load_config(home=Path.cwd() / ".campus")
config.browser_channel = "msedge"
config.initialize()
print(
    json.dumps(
        {
            "credentials": {
                name: "PRESENT" if os.getenv(name) else "MISSING"
                for name in (
                    "UTFPR_USERNAME",
                    "UTFPR_PASSWORD",
                    "MOODLE_USERNAME",
                    "MOODLE_PASSWORD",
                )
            }
        }
    )
)
try:
    # Interactive context allows the authentication POST; headless operation is overridden below
    # by using a normal session and removing the read-only route only during the login form.
    with browser(config, args.provider) as ctx:
        page = ctx.new_page()
        url = (
            config.portal_url
            if args.provider == "portal"
            else config.moodle_url + "/login/index.php"
        )
        response = page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        print(
            json.dumps(
                {
                    "provider": args.provider,
                    "path": urlsplit(page.url).path,
                    "inputs": page.locator("input").evaluate_all(
                        "es => es.map(e => ({name:e.name,type:e.type,id:e.id,control:e.getAttribute('formcontrolname')}))"
                    ),
                    "authenticated": authenticated(page, args.provider),
                }
            )
        )
        if args.login and not authenticated(page, args.provider):
            prefix = "UTFPR" if args.provider == "portal" else "MOODLE"
            username, password = os.getenv(prefix + "_USERNAME"), os.getenv(prefix + "_PASSWORD")
            users = page.locator('input[type="text"]:visible, input[type="email"]:visible')
            passwords = page.locator('input[type="password"]:visible')
            host = urlsplit(page.url).hostname or ""
            if (
                username
                and password
                and users.count() == 1
                and passwords.count() == 1
                and host.endswith(".utfpr.edu.br")
            ):
                ctx.unroute("**/*")
                users.fill(username)
                passwords.fill(password)
                passwords.press("Enter")
                page.wait_for_timeout(6000)
                print(
                    json.dumps(
                        {
                            "provider": args.provider,
                            "login_attempted": True,
                            "authenticated": authenticated(page, args.provider),
                            "host": urlsplit(page.url).hostname,
                            "path": urlsplit(page.url).path,
                            "password_form_present": page.locator('input[type="password"]').count()
                            > 0,
                            "table_count": page.locator("table").count(),
                            "frame_count": len(page.frames),
                        }
                    )
                )
            else:
                print(
                    json.dumps(
                        {
                            "state": "BLOCKED",
                            "reason": "Credential form not unambiguously identified",
                        }
                    )
                )
        if args.inspect:
            import re

            from bs4 import BeautifulSoup

            soup = BeautifulSoup(page.content(), "html.parser")
            if args.provider == "portal":
                from campus.providers.parsing import plain

                print(
                    json.dumps(
                        {
                            "visible_navigation_text": plain(page.locator("body").inner_text())[
                                :1800
                            ],
                            "interactive_elements": page.locator(
                                'button, [role="button"], select'
                            ).evaluate_all(
                                "es => es.map(e => ({tag:e.tagName,id:e.id,role:e.getAttribute('role'),text:e.textContent.trim().slice(0,80)}))"
                            ),
                        }
                    )
                )
            terms = re.compile(
                r"hist[oó]rico|hor[aá]rio|nota|falta|sair|logout|matr[ií]cula|disciplina|curr[ií]culo|boletim|aluno|acad[eê]mico|selecion|curso|campus",
                re.I,
            )
            links = [
                {
                    "label": a.get_text(" ", strip=True)[:100],
                    "path": urlsplit(a.get("href", "")).path,
                    "has_onclick": bool(a.get("onclick")),
                }
                for a in soup.select("a")
                if terms.search(a.get_text(" ", strip=True))
            ]
            print(
                json.dumps(
                    {
                        "academic_navigation": links,
                        "http_status": response.status if response else None,
                        "text_length": len(soup.get_text()),
                        "error_markers": [
                            w
                            for w in (
                                "ORA-",
                                "404",
                                "Not Found",
                                "não encontrada",
                                "não existe",
                                "Web Server",
                                "Forbidden",
                            )
                            if w.lower() in soup.get_text().lower()
                        ],
                        "forms": [
                            {
                                "action_path": urlsplit(f.get("action", "")).path,
                                "method": f.get("method"),
                                "select_names": [s.get("name") for s in f.select("select")],
                            }
                            for f in soup.select("form")
                        ],
                        "headings": [
                            h.get_text(" ", strip=True)
                            for h in soup.select("h1,h2,h3,th")
                            if terms.search(h.get_text())
                        ],
                        "auth_error": bool(
                            re.search(
                                r"senha incorreta|usu[aá]rio inv[aá]lido|acesso negado|n[aã]o autorizado",
                                soup.get_text(),
                                re.I,
                            )
                        ),
                        "select_option_counts": [
                            len(s.select("option")) for s in soup.select("select")
                        ],
                        "iframe_paths": [
                            urlsplit(f.get("src", "")).path for f in soup.select("iframe,frame")
                        ],
                        "button_texts": [
                            b.get_text(" ", strip=True)[:70]
                            for b in soup.select("button")
                            if terms.search(b.get_text())
                        ],
                    },
                    ensure_ascii=True,
                )
            )
            if args.provider == "portal" and len(soup.get_text()) < 500:
                from campus.security import has_secret, redact

                body = redact(soup.get_text(" ", strip=True))
                if not has_secret(body.encode()):
                    print(json.dumps({"short_landing_message": body}))
                # The actual public home page supplies the student route; do not guess endpoints.
                page.goto("https://sistemas2.utfpr.edu.br/", wait_until="domcontentloaded")
                print(
                    json.dumps(
                        {
                            "student_links": page.locator('a[href*="aluno"]').evaluate_all(
                                "es => es.map(e => ({path:new URL(e.href).pathname}))"
                            )
                        }
                    )
                )
except Exception as exc:
    print(json.dumps({"state": "FAILED", "error_type": type(exc).__name__}))
