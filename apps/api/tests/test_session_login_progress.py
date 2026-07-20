"""The login records why it ended the way it did.

Until now a failed login left nothing behind: the status flipped to
needs_manual_action and the reason — which step timed out, on which Passport
URL — existed only in the return value that login_operator discarded. The
operator had no way to tell a wrong password from a changed page layout.
"""

from app.models.enums import SessionStatus
from app.services.scrape_service import ScrapeService


class _FakeScraper:
    """Stands in for Playwright, driving the same on_step callback contract."""

    def __init__(self, status, message):
        self._status = status
        self._message = message

    def login_with_password(self, login, password, path, request_code=None, on_step=None):
        if on_step:
            on_step("passport_opened", "https://passport.yandex.ru/pwl-yandex/auth/add")
            on_step("login_submitted", "https://passport.yandex.ru/pwl-yandex/auth/push-code")
        return self._status, self._message


def test_login_persists_the_failure_message(db_session):
    service = ScrapeService(db_session)
    service.auth_scraper = _FakeScraper(SessionStatus.needs_manual_action, "Timed out on the password screen")

    service.login_operator()

    session = ScrapeService(db_session).get_session_record()
    assert session.status == SessionStatus.needs_manual_action
    assert session.last_message == "Timed out on the password screen"


def test_login_records_each_step_with_its_url(db_session):
    service = ScrapeService(db_session)
    service.auth_scraper = _FakeScraper(SessionStatus.valid, "Login successful")

    service.login_operator()

    progress = ScrapeService(db_session).get_session_record().progress
    assert [entry["step"] for entry in progress] == ["passport_opened", "login_submitted"]
    assert progress[1]["url"].endswith("/auth/push-code")
    assert all(entry["at"] for entry in progress)


def test_progress_resets_between_logins(db_session):
    service = ScrapeService(db_session)
    service.auth_scraper = _FakeScraper(SessionStatus.valid, "Login successful")
    service.login_operator()
    service.login_operator()

    progress = ScrapeService(db_session).get_session_record().progress
    assert len(progress) == 2, "a new attempt must not append to the previous attempt's trace"


def test_session_endpoint_exposes_message_and_progress(admin_client, db_session):
    service = ScrapeService(db_session)
    service.auth_scraper = _FakeScraper(SessionStatus.needs_manual_action, "Confirmation code required")
    service.login_operator()

    body = admin_client.get("/api/scraper/yandex/session").json()

    assert body["message"] == "Confirmation code required"
    assert [entry["step"] for entry in body["progress"]] == ["passport_opened", "login_submitted"]
