import json
import os
import re
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

from campus.config import Config
from campus.models import CampusError, State, now
from campus.security import private_dir, safe_url


def debug_metadata(config: Config, provider: str, operation: str, error_type: str):
    folder = private_dir(config.home / "debug" / (now().replace(":", "-") + "-" + provider))
    (folder / "metadata.json").write_text(
        json.dumps(
            {
                "provider": provider,
                "operation": operation,
                "error_type": error_type,
                "time": now(),
                "capture_policy": "No page content, URLs, screenshots, credentials or traces captured",
            },
            indent=2,
        ),
        encoding="utf-8",
    )


@contextmanager
def browser(config: Config, provider: str, *, interactive=False):
    from playwright.sync_api import sync_playwright

    profile = private_dir(config.home / "auth" / provider)
    # POSIX directory permissions; on Windows retain and inspect the user's inherited ACL.
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                str(profile),
                headless=not interactive,
                channel=config.browser_channel,
                accept_downloads=False,
                args=["--disable-extensions"],
                timeout=30000,
            )
            try:
                cookie_file = profile / "session-cookies.json"
                if cookie_file.exists():
                    ctx.add_cookies(json.loads(cookie_file.read_text(encoding="utf-8")))
                if not interactive:

                    def guard(route):
                        request = route.request
                        parts = urlsplit(request.url)
                        # Observed Gmail list-view batch fetch. Action/mutation
                        # endpoints remain blocked; CAMPUS never opens threads.
                        gmail_list_read = (
                            provider == "mail"
                            and parts.hostname == "mail.google.com"
                            and re.fullmatch(r"/sync/u/\d+/i/bv", parts.path)
                            and request.method == "POST"
                        )
                        portal_menu_read = (
                            provider == "portal"
                            and parts.hostname == urlsplit(config.portal_url).hostname
                            and parts.path
                            == urlsplit(config.portal_url).path.rsplit("/", 1)[0]
                            + "/mpmenu.pcAjaxMenu"
                            and request.method == "POST"
                        )
                        if request.method not in ("GET", "HEAD") and not (
                            gmail_list_read or portal_menu_read
                        ):
                            route.abort()
                        else:
                            route.continue_()

                    ctx.route("**/*", guard)
                yield ctx
            finally:
                # Browser engines drop session cookies on restart even with persistent profiles.
                # Persist them only inside the private auth directory, never in evidence/debug files.
                cookie_file = profile / "session-cookies.json"
                cookie_file.write_text(json.dumps(ctx.cookies()), encoding="utf-8")
                if os.name != "nt":
                    cookie_file.chmod(0o600)
                ctx.close()
    except CampusError:
        raise
    except Exception as exc:
        debug_metadata(config, provider, "browser session", type(exc).__name__)
        raise CampusError(
            f"{provider}: browser session failed ({type(exc).__name__}). Install Chromium with 'python -m playwright install chromium', or configure browser_channel='msedge'; close other CAMPUS sessions using this profile. Debug metadata contains no page content."
        ) from None


def authenticated(page, provider: str) -> bool:
    host = urlsplit(page.url).hostname or ""
    if page.locator('input[type="password"]').count():
        return False
    if provider == "mail":
        labels = page.locator(
            'a[href*="accounts.google.com"], button[aria-label*="@"], a[aria-label*="@"]'
        )
        institutional = False
        for label in labels.all():
            text = label.get_attribute("aria-label") or ""
            if re.search(r"[\w.+-]+@alunos\.utfpr\.edu\.br\b", text, re.I):
                institutional = True
                break
        return (
            host == "mail.google.com"
            and institutional
            and page.locator('a[href*="#inbox"], [role="main"] [role="row"]').count() > 0
        )
    if provider == "moodle":
        return page.locator('a[href*="/login/logout.php"]').count() > 0
    return (
        host.endswith("utfpr.edu.br")
        and page.locator(
            'button#logoutButton, a[href*="logout"], a[href*="sair"], a[href*="logoff"]'
        ).count()
        > 0
    )


def portal_landing(config: Config) -> str:
    route = config.home / "auth" / "portal" / "academic-route.json"
    if route.exists():
        value = json.loads(route.read_text(encoding="utf-8"))["url"]
        host = urlsplit(value).hostname or ""
        if urlsplit(value).scheme == "https" and host.endswith(".utfpr.edu.br"):
            return value
    return config.portal_url


def auth(config: Config, provider: str, wait_seconds=180) -> dict:
    if provider not in {"portal", "moodle", "mail"}:
        raise CampusError("Choose portal, moodle or mail")
    url = {
        "portal": portal_landing(config),
        "moodle": config.moodle_url + "/my/",
        "mail": "https://mail.google.com/",
    }[provider]
    with browser(config, provider, interactive=True) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, wait_until="domcontentloaded")
        if provider == "portal" and config.portal_campus:
            from campus.engines import normalize

            for link in page.locator("a[href]").all():
                if normalize(link.inner_text()) == normalize(config.portal_campus):
                    from urllib.parse import urljoin

                    target = urljoin(page.url, link.get_attribute("href"))
                    if urlsplit(target).scheme == "https" and (
                        urlsplit(target).hostname or ""
                    ).endswith(".utfpr.edu.br"):
                        page.goto(target, wait_until="domcontentloaded")
                    break
        # Credentials remain in-process. Google authentication is always manual.
        if provider != "mail":
            prefix = "UTFPR" if provider == "portal" else "MOODLE"
            username, password = os.getenv(prefix + "_USERNAME"), os.getenv(prefix + "_PASSWORD")
            if (
                username
                and password
                and (urlsplit(page.url).hostname or "").endswith(".utfpr.edu.br")
            ):
                users = page.locator(
                    'input[name="username"]:visible, input[name="Username"]:visible, input[name="login"]:visible, input#login-username:visible'
                )
                passwords = page.locator('input[type="password"]:visible')
                if users.count() == 1 and passwords.count() == 1:
                    users.fill(username)
                    passwords.fill(password)
                    # Only submit the actual credential form, never arbitrary campus forms.
                    passwords.press("Enter")
        until = time.monotonic() + wait_seconds
        while time.monotonic() < until:
            if authenticated(page, provider):
                if provider == "portal":
                    (config.home / "auth" / "portal" / "academic-route.json").write_text(
                        json.dumps({"url": safe_url(page.url)}), encoding="utf-8"
                    )
                return {
                    "provider": provider,
                    "state": "HEALTHY",
                    "authenticated": True,
                    "message": "Authenticated UI marker verified; session persisted in the private browser profile",
                }
            page.wait_for_timeout(1000)
        return {
            "provider": provider,
            "state": State.BLOCKED,
            "authenticated": False,
            "message": "Complete sign-in/MFA/CAPTCHA using campus auth; no security control was bypassed",
        }
