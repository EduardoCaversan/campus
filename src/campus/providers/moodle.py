import os
import time
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from campus.models import CampusError, ProviderResult, State
from campus.providers.browser import authenticated, browser
from campus.providers.parsing import (
    fact,
    moodle_assignment,
    moodle_course_facts,
    moodle_courses,
    plain,
)

READ_METHODS = {
    "core_webservice_get_site_info",
    "core_enrol_get_users_courses",
    "mod_assign_get_assignments",
    "mod_assign_get_submission_status",
    "core_course_get_contents",
    "gradereport_user_get_grade_items",
    "core_course_get_enrolled_courses_by_timeline_classification",
}


def timestamp(value):
    return datetime.fromtimestamp(value, UTC).isoformat() if value else None


class MoodleProvider:
    name = "moodle"

    def __init__(self, config):
        self.config = config

    def rpc(self, client, method: str, **kwargs):
        if method not in READ_METHODS:
            raise CampusError("Moodle method is outside the read-only allowlist", State.BLOCKED)
        data = {
            "wstoken": os.environ["MOODLE_TOKEN"],
            "wsfunction": method,
            "moodlewsrestformat": "json",
        }
        data.update(kwargs)
        # Token goes in the HTTPS request body, never a URL, log, snapshot or exception.
        response = client.post(self.config.moodle_url + "/webservice/rest/server.php", data=data)
        response.raise_for_status()
        result = response.json()
        if isinstance(result, dict) and result.get("exception"):
            raise CampusError(
                "Moodle denied a read method; token may be expired or lack service permission",
                State.BLOCKED,
            )
        return result

    def check(self):
        if os.getenv("MOODLE_TOKEN"):
            try:
                with httpx.Client(timeout=25, follow_redirects=False) as client:
                    info = self.rpc(client, "core_webservice_get_site_info")
                    verified = bool(info.get("userid"))
                return ProviderResult(
                    provider=self.name,
                    state=State.HEALTHY if verified else State.BLOCKED,
                    authenticated=verified,
                    message="Moodle token identity verified"
                    if verified
                    else "Moodle identity not returned",
                )
            except Exception:
                return ProviderResult(
                    provider=self.name,
                    state=State.BLOCKED,
                    message="Moodle token verification failed; details suppressed",
                )
        return self._browser_sync(check_only=True)

    def sync(self):
        return self._token_sync() if os.getenv("MOODLE_TOKEN") else self._browser_sync()

    def _token_sync(self):
        facts, warnings = [], []
        try:
            with httpx.Client(timeout=25, follow_redirects=False) as client:
                info = self.rpc(client, "core_webservice_get_site_info")
                uid = info["userid"]
                courses = self.rpc(client, "core_enrol_get_users_courses", userid=uid)
                if len(courses) > self.config.max_items:
                    warnings.append("Course limit reached; increase max_items to retrieve the rest")
                for course in courses[: self.config.max_items]:
                    cid = course["id"]
                    subject = f"moodle:course:{cid}"
                    ref = self.config.moodle_url + f"/course/view.php?id={cid}"
                    facts.extend(moodle_course_facts(cid, course["fullname"], ref))
                    if course.get("shortname"):
                        facts.append(
                            fact(
                                subject, "course", "shortname", course["shortname"], self.name, ref
                            )
                        )
                    try:
                        response = self.rpc(
                            client, "mod_assign_get_assignments", **{"courseids[0]": cid}
                        )
                        for entry in response.get("courses", []):
                            for assignment in entry.get("assignments", []):
                                aid, cmid = assignment["id"], assignment["cmid"]
                                target = f"moodle:assignment:{cmid}"
                                url = self.config.moodle_url + f"/mod/assign/view.php?id={cmid}"
                                values = {
                                    "name": assignment["name"],
                                    "course": subject,
                                    "description": plain(assignment.get("intro", "")),
                                    "due_at": timestamp(assignment.get("duedate")),
                                    "opens_at": timestamp(
                                        assignment.get("allowsubmissionsfromdate")
                                    ),
                                    "attachments": [
                                        f["fileurl"]
                                        for f in assignment.get("introattachments", [])
                                        if f.get("fileurl")
                                    ],
                                }
                                for field, value in values.items():
                                    if value is not None:
                                        facts.append(
                                            fact(target, "assignment", field, value, self.name, url)
                                        )
                                try:
                                    status = self.rpc(
                                        client,
                                        "mod_assign_get_submission_status",
                                        assignid=aid,
                                        userid=uid,
                                    )
                                    submission = status.get("lastattempt", {}).get("submission", {})
                                    if submission.get("status"):
                                        facts.append(
                                            fact(
                                                target,
                                                "assignment",
                                                "submission_state",
                                                submission["status"],
                                                self.name,
                                                url,
                                            )
                                        )
                                    feedback = status.get("feedback", {})
                                    if feedback:
                                        facts.append(
                                            fact(
                                                target,
                                                "assignment",
                                                "feedback",
                                                plain(str(feedback)),
                                                self.name,
                                                url,
                                            )
                                        )
                                except CampusError:
                                    warnings.append(
                                        f"Submission status unavailable for Moodle activity {cmid}"
                                    )
                        contents = self.rpc(client, "core_course_get_contents", courseid=cid)
                        for section in contents:
                            for module in section.get("modules", []):
                                if module.get("modname") in {"resource", "folder", "page", "forum"}:
                                    facts.append(
                                        fact(
                                            f"moodle:resource:{module['id']}",
                                            "resource",
                                            "details",
                                            {
                                                "name": module.get("name"),
                                                "course": subject,
                                                "section": section.get("name"),
                                                "description": plain(module.get("description", "")),
                                                "files": [
                                                    {
                                                        "name": f.get("filename"),
                                                        "url": f.get("fileurl"),
                                                        "size": f.get("filesize"),
                                                    }
                                                    for f in module.get("contents", [])
                                                ],
                                            },
                                            self.name,
                                            module.get("url") or ref,
                                        )
                                    )
                    except CampusError:
                        warnings.append(
                            f"Assignment or content service unavailable for Moodle course {cid}"
                        )
                    time.sleep(0.25)
            return ProviderResult(
                provider=self.name,
                state=State.PARTIAL if warnings else State.HEALTHY,
                authenticated=True,
                facts=facts,
                warnings=warnings,
                message="Read-only Moodle web service synchronization",
            )
        except Exception as exc:
            return ProviderResult(
                provider=self.name,
                state=State.PARTIAL if facts else State.FAILED,
                facts=facts,
                warnings=warnings,
                message=f"Moodle read synchronization failed ({type(exc).__name__}); no remote content was changed",
            )

    def _browser_sync(self, check_only=False):
        if not (self.config.home / "auth" / "moodle" / "Default").exists():
            return ProviderResult(
                provider=self.name,
                state=State.BLOCKED,
                authenticated=False,
                message="No Moodle browser session. Run campus auth moodle or supply an existing MOODLE_TOKEN",
            )
        facts, warnings = [], []
        try:
            with browser(self.config, self.name) as ctx:
                page = ctx.new_page()
                page.goto(self.config.moodle_url + "/my/courses.php", wait_until="domcontentloaded")
                if not authenticated(page, self.name):
                    return ProviderResult(
                        provider=self.name,
                        state=State.BLOCKED,
                        authenticated=False,
                        message="Moodle login/MFA required: campus auth moodle",
                    )
                if check_only:
                    return ProviderResult(
                        provider=self.name,
                        state=State.HEALTHY,
                        authenticated=True,
                        message="Moodle authenticated logout marker verified",
                    )
                # Moodle's documented AJAX course endpoint is preferable to virtualized dashboard cards.
                key = page.evaluate("() => window.M?.cfg?.sesskey || null")
                links = []
                if key:
                    offset = 0
                    while offset < self.config.max_items:
                        response = ctx.request.post(
                            self.config.moodle_url + "/lib/ajax/service.php",
                            params={"sesskey": key},
                            data=[
                                {
                                    "index": 0,
                                    "methodname": "core_course_get_enrolled_courses_by_timeline_classification",
                                    "args": {
                                        "classification": "all",
                                        "limit": min(50, self.config.max_items - offset),
                                        "offset": offset,
                                        "sort": "fullname",
                                    },
                                }
                            ],
                        )
                        payload = response.json()
                        if not isinstance(payload, list) or not payload or payload[0].get("error"):
                            warnings.append(
                                "Enrolled-course AJAX unavailable; using visible course links"
                            )
                            break
                        data = payload[0].get("data", {})
                        courses = data.get("courses", [])
                        for c in courses:
                            ref = self.config.moodle_url + f"/course/view.php?id={c['id']}"
                            facts.extend(moodle_course_facts(c["id"], c["fullname"], ref))
                            links.append((ref, f"moodle:course:{c['id']}"))
                        if (
                            not courses
                            or not data.get("nextoffset")
                            or data["nextoffset"] <= offset
                        ):
                            break
                        offset = data["nextoffset"]
                        time.sleep(0.25)
                    if offset >= self.config.max_items:
                        warnings.append("Course pagination limit reached")
                if not links:
                    parsed = moodle_courses(page.content(), self.config.moodle_url)
                    facts.extend(parsed)
                    links = sorted({(f.external_ref, f.subject) for f in parsed})
                if not links:
                    warnings.append(
                        "No enrolled courses could be verified; empty dashboard is not proof of no enrollment"
                    )
                for ref, course in links[: self.config.max_items]:
                    page.goto(ref, wait_until="domcontentloaded")
                    html = page.content()
                    from campus.providers.moodle_content import course_content

                    content_facts, content_warnings = course_content(
                        ctx, self.config, html, ref, course
                    )
                    facts.extend(content_facts)
                    warnings.extend(content_warnings)
                    soup = BeautifulSoup(html, "html.parser")
                    assignment_urls = sorted(
                        {
                            urljoin(ref, a["href"])
                            for a in soup.select('a[href*="/mod/assign/view.php?id="]')
                        }
                    )
                    if len(assignment_urls) > self.config.max_items:
                        warnings.append("Assignment limit reached")
                    for url in assignment_urls[: self.config.max_items]:
                        if urlsplit(url).hostname != urlsplit(self.config.moodle_url).hostname:
                            continue
                        page.goto(url, wait_until="domcontentloaded")
                        if not authenticated(page, self.name):
                            raise CampusError("Moodle session expired", State.BLOCKED)
                        facts.extend(
                            moodle_assignment(page.content(), url, course, self.config.timezone)
                        )
                        time.sleep(0.3)
                warnings.append(
                    "Browser extraction covers visible assignments/resources, bounded teaching documents and announcement-index titles. Discussion bodies are not opened; feedback and hidden sections may be incomplete. Recognized Portuguese deadlines use configured timezone"
                )
            return ProviderResult(
                provider=self.name,
                state=State.PARTIAL if warnings else State.HEALTHY,
                authenticated=True,
                facts=facts,
                warnings=warnings,
                message="Moodle browser extraction finished",
            )
        except Exception as exc:
            return ProviderResult(
                provider=self.name,
                state=State.PARTIAL if facts else State.FAILED,
                facts=facts,
                message=f"Moodle browser extraction failed ({type(exc).__name__}); inspect sanitized debug metadata",
            )
