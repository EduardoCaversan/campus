import email
import imaplib
import os
import ssl
from datetime import UTC, datetime, timedelta
from email import policy
from urllib.parse import quote

from campus.models import CampusError, ProviderResult, State
from campus.providers.browser import authenticated, browser
from campus.providers.parsing import academic_mail, fact, plain
from campus.security import digest


class StudentMailProvider:
    name = "mail"

    def __init__(self, config, course_terms=()):
        self.config = config
        self.course_terms = course_terms

    def check(self):
        return self._imap(True) if self.config.mail_mode == "imap" else self._browser(True)

    def sync(self):
        return self._imap() if self.config.mail_mode == "imap" else self._browser()

    def _imap(self, check_only=False):
        address, password = os.getenv("CAMPUS_MAIL_ADDRESS"), os.getenv("CAMPUS_MAIL_APP_PASSWORD")
        if not address or not password:
            return ProviderResult(
                provider=self.name,
                state=State.BLOCKED,
                authenticated=False,
                message="IMAP requires CAMPUS_MAIL_ADDRESS and an existing institution-authorized CAMPUS_MAIL_APP_PASSWORD; never supply your Google password",
            )
        if not address.lower().endswith("@alunos.utfpr.edu.br"):
            raise CampusError("Mail account must be an @alunos.utfpr.edu.br address", State.BLOCKED)
        facts, client = [], None
        try:
            client = imaplib.IMAP4_SSL(
                "imap.gmail.com", ssl_context=ssl.create_default_context(), timeout=25
            )
            client.login(address, password)
            if check_only:
                return ProviderResult(
                    provider=self.name,
                    state=State.HEALTHY,
                    authenticated=True,
                    message="Gmail IMAP authentication verified",
                )
            status, _ = client.select("INBOX", readonly=True)
            if status != "OK":
                raise CampusError("Read-only inbox access denied")
            since = (datetime.now(UTC) - timedelta(days=self.config.mail_days)).strftime("%d-%b-%Y")
            status, data = client.uid("search", None, "SINCE", since)
            if status != "OK":
                raise CampusError("Mail search failed")
            all_ids = data[0].split()
            for uid in all_ids[-self.config.max_items :]:
                status, payload = client.uid(
                    "fetch",
                    uid,
                    "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)] RFC822.SIZE)",
                )
                chunks = [p for p in payload if isinstance(p, tuple)]
                if status != "OK" or not chunks:
                    continue
                header = email.message_from_bytes(chunks[0][1], policy=policy.default)
                sender, subject = str(header.get("From", "")), str(header.get("Subject", ""))
                if not academic_mail(sender, subject, "", self.course_terms):
                    continue
                # Bound body retrieval; PEEK and EXAMINE never mark messages read.
                status, body_data = client.uid("fetch", uid, "(BODY.PEEK[TEXT]<0.262144>)")
                body_bytes = (
                    b"".join(p[1] for p in body_data if isinstance(p, tuple))
                    if status == "OK"
                    else b""
                )
                msg = email.message_from_bytes(
                    chunks[0][1] + b"\r\n" + body_bytes, policy=policy.default
                )
                text = body_bytes.decode("utf-8", errors="replace")
                if msg.is_multipart():
                    text = "\n".join(
                        p.get_payload(decode=True).decode(
                            p.get_content_charset() or "utf-8", errors="replace"
                        )
                        for p in msg.walk()
                        if p.get_content_type() == "text/plain" and p.get_payload(decode=True)
                    )
                identity = str(header.get("Message-ID") or digest(chunks[0][1].hex()))
                target = "mail:" + digest(identity)[:24]
                ref = "gmail-message:" + digest(identity)
                for field, value in {
                    "sender": sender,
                    "subject": subject,
                    "date": str(header.get("Date", "")),
                    "body_excerpt": plain(text),
                }.items():
                    facts.append(fact(target, "mail", field, value, self.name, ref))
            warnings = [
                "Only INBOX is inspected; bodies are bounded to 256 KiB and remain untrusted evidence. Dates/events are not inferred from prose."
            ]
            if len(all_ids) > self.config.max_items:
                warnings.append(
                    "Message limit reached; older messages in the search window were not fetched"
                )
            return ProviderResult(
                provider=self.name,
                state=State.PARTIAL,
                authenticated=True,
                facts=facts,
                warnings=warnings,
                message="Academic inbox messages retrieved using read-only IMAP and BODY.PEEK",
            )
        except Exception as exc:
            return ProviderResult(
                provider=self.name,
                state=State.PARTIAL if facts else State.BLOCKED,
                facts=facts,
                message=f"Gmail IMAP unavailable ({type(exc).__name__}); organization policy may prohibit app passwords. Use manual browser authentication",
            )
        finally:
            if client:
                try:
                    client.logout()
                except (OSError, imaplib.IMAP4.error):
                    pass  # Logout failure cannot change an already completed read.

    def _browser(self, check_only=False):
        if not (self.config.home / "auth" / "mail" / "Default").exists():
            return ProviderResult(
                provider=self.name,
                state=State.BLOCKED,
                authenticated=False,
                message="Manual Google authentication required: campus auth mail. No Google password is requested or stored by CAMPUS",
            )
        facts = []
        try:
            with browser(self.config, self.name) as ctx:
                page = ctx.new_page()
                query = f"newer_than:{self.config.mail_days}d {{from:(utfpr.edu.br) subject:(UTFPR Moodle)}}"
                page.goto(
                    "https://mail.google.com/mail/u/0/#search/" + quote(query, safe=""),
                    wait_until="domcontentloaded",
                )
                page.wait_for_timeout(3000)
                if not authenticated(page, self.name):
                    return ProviderResult(
                        provider=self.name,
                        state=State.BLOCKED,
                        authenticated=False,
                        message="Gmail authenticated inbox not verified. Complete campus auth mail; browser restrictions may also prevent mailbox loading",
                    )
                if check_only:
                    return ProviderResult(
                        provider=self.name,
                        state=State.HEALTHY,
                        authenticated=True,
                        message="Gmail authenticated inbox marker verified",
                    )
                rows = page.locator('[role="main"] tr.zA')
                for i in range(min(rows.count(), self.config.max_items)):
                    row = rows.nth(i)
                    text = row.inner_text()
                    sender = (
                        row.locator("[email]").first.get_attribute("email")
                        if row.locator("[email]").count()
                        else ""
                    )
                    if not academic_mail(sender, text, "", self.course_terms):
                        continue
                    thread_id = row.get_attribute("data-legacy-thread-id") or row.get_attribute(
                        "data-thread-id"
                    )
                    if not thread_id:
                        identifiers = row.locator("[data-legacy-thread-id], [data-thread-id]")
                        if identifiers.count():
                            thread_id = identifiers.first.get_attribute(
                                "data-legacy-thread-id"
                            ) or identifiers.first.get_attribute("data-thread-id")
                    if not thread_id:
                        continue  # A changing snippet cannot serve as a stable message identity.
                    target = "mail:thread:" + digest(thread_id)[:24]
                    facts.extend(
                        [
                            fact(
                                target,
                                "mail",
                                "sender",
                                sender,
                                self.name,
                                "gmail-thread:" + digest(thread_id),
                            ),
                            fact(
                                target,
                                "mail",
                                "snippet",
                                text,
                                self.name,
                                "gmail-thread:" + digest(thread_id),
                            ),
                        ]
                    )
            return ProviderResult(
                provider=self.name,
                state=State.PARTIAL,
                authenticated=True,
                facts=facts,
                message="Gmail visible academic thread snippets inspected",
                warnings=[
                    "Browser mode never opens threads (opening can mark mail as read). Bodies, attachments, pagination and empty-result completeness are unverified; use read-only IMAP for message content."
                ],
            )
        except Exception as exc:
            return ProviderResult(
                provider=self.name,
                state=State.PARTIAL if facts else State.FAILED,
                facts=facts,
                message=f"Gmail browser list inspection failed ({type(exc).__name__}); no thread was opened",
            )
