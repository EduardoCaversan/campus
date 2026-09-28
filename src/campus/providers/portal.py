import time
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from campus.models import ProviderResult, State
from campus.providers.browser import authenticated, browser, portal_landing
from campus.providers.parsing import fact
from campus.providers.portal_parsing import academic_links, decode_html, parse_bundle


class UtfprPortalProvider:
    name = "portal"

    def __init__(self, config):
        self.config = config

    def check(self):
        return self._read(check_only=True)

    def sync(self):
        return self._read()

    def _read(self, check_only=False):
        if not (self.config.home / "auth" / "portal" / "Default").exists():
            return ProviderResult(
                provider=self.name,
                state=State.BLOCKED,
                authenticated=False,
                message="Portal needs a verified browser session: campus auth portal",
            )
        facts, warnings = [], []
        try:
            with browser(self.config, self.name) as ctx:
                page = ctx.new_page()
                page.goto(portal_landing(self.config), wait_until="domcontentloaded")
                if not authenticated(page, self.name):
                    return ProviderResult(
                        provider=self.name,
                        state=State.BLOCKED,
                        authenticated=False,
                        message="Portal academic session not verified. Select your campus in campus auth portal and complete any login/SSO confirmation",
                    )
                if check_only:
                    return ProviderResult(
                        provider=self.name,
                        state=State.HEALTHY,
                        authenticated=True,
                        message="Authenticated portal logout marker verified",
                    )
                page.locator(".card-content").first.wait_for(state="attached", timeout=15000)
                links = academic_links(page.content(), page.url)
                iframe = page.locator("#if_navega").get_attribute("src") or ""
                campus = parse_qs(urlsplit(iframe).query).get("p_unidadelogado", [None])[0]
                if campus:
                    facts.append(
                        fact(
                            "portal:academic-context",
                            "context",
                            "campus_id",
                            campus,
                            self.name,
                            page.url,
                            "Campus identifier supplied by authenticated menu iframe",
                        )
                    )
                pages = {}
                for label, url in links.items():
                    try:
                        response = ctx.request.get(url, max_redirects=0, timeout=30000)
                        if response.status != 200:
                            warnings.append(
                                f"{label}: academic view unavailable or authentication redirected"
                            )
                            continue
                        html = decode_html(
                            response.body(), response.headers.get("content-type", "")
                        )
                        if BeautifulSoup(html, "html.parser").select_one('input[type="password"]'):
                            warnings.append(f"{label}: sign-in required")
                            continue
                        pages[label] = (html, url)
                    except Exception as exc:
                        warnings.append(f"{label}: read failed ({type(exc).__name__})")
                    time.sleep(0.3)
                facts.extend(parse_bundle(pages))
                if len(pages) < 4:
                    warnings.append("Not all four supported academic views were retrieved")
                if not any(f.kind == "course" for f in facts):
                    warnings.append(
                        "No current enrollment rows recognized; empty extraction does not prove no enrollment"
                    )
                warnings.append(
                    "Future offerings, complete grade policies, equivalent-course credit rules and non-course graduation requirements may still be unknown"
                )
            return ProviderResult(
                provider=self.name,
                state=State.PARTIAL,
                authenticated=True,
                facts=facts,
                message="Read-only portal bulletin, enrollment, history and curriculum synchronization",
                warnings=warnings,
            )
        except Exception as exc:
            return ProviderResult(
                provider=self.name,
                state=State.PARTIAL if facts else State.FAILED,
                facts=facts,
                message=f"Portal academic-page read failed ({type(exc).__name__}); expected an authenticated page with recognizable academic tables",
            )
