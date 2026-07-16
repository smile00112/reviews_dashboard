import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import OrganizationScrapeStatus, ReviewPlatform, ScrapeMode, ScrapeRunStatus, SessionStatus
from app.models.scrape_run import ScrapeRun
from app.models.scraper_session import ScraperSession
from app.scraper.types import ScrapeResult
from app.scraper.twogis_api import TwogisApiScraper
from app.scraper.yandex_auth import YandexAuthScraper
from app.scraper.yandex_http import YandexHttpScraper
from app.scraper.yandex_public import YandexPublicScraper
from app.scraper.yandex_scrapeops import YandexScrapeOpsScraper
from app.services.dashboard_service import DashboardService
from app.services.organization_service import OrganizationService
from app.services.review_service import ReviewService


logger = logging.getLogger(__name__)


def _mode_platform(mode: ScrapeMode) -> str:
    """Which platform a scrape mode targets: only twogis_api hits 2GIS."""
    return "2gis" if mode == ScrapeMode.twogis_api else "yandex"


def _mode_url(org, mode: ScrapeMode) -> str | None:
    """The org link a scrape mode must follow — each mode reads its own platform's
    column. Handing every mode ``yandex_url`` makes a 2GIS run scrape Yandex."""
    return org.gis2_url if mode == ScrapeMode.twogis_api else org.yandex_url


class ScrapeService:
    def __init__(
        self,
        db: Session,
        public_scraper: YandexPublicScraper | None = None,
        http_scraper: YandexHttpScraper | None = None,
        scrapeops_scraper: YandexScrapeOpsScraper | None = None,
        twogis_scraper: TwogisApiScraper | None = None,
    ):
        self.db = db
        self.public_scraper = public_scraper or YandexPublicScraper()
        self.http_scraper = http_scraper or YandexHttpScraper()
        self.auth_scraper = YandexAuthScraper()
        self.scrapeops_scraper = scrapeops_scraper or YandexScrapeOpsScraper()
        self.twogis_scraper = twogis_scraper or TwogisApiScraper()

    def create_run(self, organization_id: UUID | None, mode: ScrapeMode) -> ScrapeRun:
        run = ScrapeRun(organization_id=organization_id, mode=mode, status=ScrapeRunStatus.queued)
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def get_run(self, run_id: UUID) -> ScrapeRun | None:
        return self.db.query(ScrapeRun).filter(ScrapeRun.id == run_id).first()

    def list_runs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        organization_id: UUID | None = None,
    ) -> list[ScrapeRun]:
        query = self.db.query(ScrapeRun)
        if organization_id:
            query = query.filter(ScrapeRun.organization_id == organization_id)
        return query.order_by(ScrapeRun.started_at.desc()).offset(offset).limit(limit).all()

    def execute_run(
        self,
        run_id: UUID,
        limit: float | None = None,
        max_pages: int | None = None,
    ) -> None:
        """Execute a queued run.

        ``limit``/``max_pages`` override the settings caps for this run only and are
        forwarded to the scrapers that paginate. Omitted (the API path) = unchanged
        behaviour; the scrapers fall back to their settings values.
        """
        overrides: dict = {}
        if limit is not None:
            overrides["limit"] = limit
        if max_pages is not None:
            overrides["max_pages"] = max_pages

        run = self.get_run(run_id)
        if not run:
            return

        run.status = ScrapeRunStatus.running
        self.db.commit()

        org_service = OrganizationService(self.db)
        review_service = ReviewService(self.db)

        if run.organization_id:
            org = org_service.get(run.organization_id)
            if not org:
                self._finalize(run, ScrapeRunStatus.failed, error_code="not_found", error_message="Organization not found")
                return
            org_service.update_scrape_status(org.id, _mode_platform(run.mode), OrganizationScrapeStatus.running)
            self._scrape_organization(
                run, _mode_url(org, run.mode), org.id, run.mode, org_service, review_service, overrides
            )
            return

        org_ids = org_service.list_ids()
        children: list[ScrapeRun] = []
        for org_id in org_ids:
            org = org_service.get(org_id)
            if not org:
                continue
            child = ScrapeRun(organization_id=org_id, mode=run.mode, status=ScrapeRunStatus.running)
            self.db.add(child)
            self.db.commit()
            self.db.refresh(child)
            self._scrape_organization(
                child, _mode_url(org, run.mode), org.id, run.mode, org_service, review_service, overrides
            )
            self.db.refresh(child)
            children.append(child)

        # Parent reflects children (FR-004): all failed -> failed; no success but a
        # manual-action child -> needs_manual_action; otherwise (>=1 success or no
        # orgs) -> success. Counters roll up child totals.
        statuses = [c.status for c in children]
        if children and all(s == ScrapeRunStatus.failed for s in statuses):
            run.status = ScrapeRunStatus.failed
        elif ScrapeRunStatus.success not in statuses and ScrapeRunStatus.needs_manual_action in statuses:
            run.status = ScrapeRunStatus.needs_manual_action
        else:
            run.status = ScrapeRunStatus.success
        run.reviews_seen = sum(c.reviews_seen or 0 for c in children)
        run.reviews_inserted = sum(c.reviews_inserted or 0 for c in children)
        run.reviews_updated = sum(c.reviews_updated or 0 for c in children)
        run.finished_at = datetime.now(timezone.utc)
        self.db.commit()

    def _scrape_organization(
        self,
        run: ScrapeRun,
        url: str,
        organization_id: UUID,
        mode: ScrapeMode,
        org_service: OrganizationService,
        review_service: ReviewService,
        overrides: dict | None = None,
    ) -> None:
        overrides = overrides or {}
        if not url:
            # No link for this mode's platform. Scraping the other platform's URL
            # would collect the wrong org's reviews, so this is a failure.
            self._finalize(
                run,
                ScrapeRunStatus.failed,
                error_code="no_url",
                error_message=f"Organization has no {_mode_platform(mode)} URL",
            )
            org_service.update_scrape_status(organization_id, _mode_platform(mode), OrganizationScrapeStatus.failed)
            return
        try:
            if mode == ScrapeMode.operator_auth:
                session = self._get_or_create_session_record()
                if session.status != SessionStatus.valid:
                    self._finalize(
                        run,
                        ScrapeRunStatus.needs_manual_action,
                        error_code="invalid_session",
                        error_message="Operator session is not valid. Run login first.",
                    )
                    org_service.update_scrape_status(
                        organization_id, _mode_platform(mode), OrganizationScrapeStatus.needs_manual_action
                    )
                    return
                scrape_result = self.auth_scraper.scrape(url, session.storage_state_path)
            elif mode == ScrapeMode.public_http:
                scrape_result = self.http_scraper.scrape(url, **overrides)
            elif mode == ScrapeMode.scrapeops:
                scrape_result = self.scrapeops_scraper.scrape(url)
            elif mode == ScrapeMode.twogis_api:
                scrape_result = self.twogis_scraper.scrape(url, **overrides)
            else:
                # Playwright modes scroll rather than paginate; they have no
                # limit/max_pages knob, so overrides do not apply (the CLI rejects
                # --all-reviews for these modes rather than silently ignoring it).
                scrape_result = self.public_scraper.scrape(url)

            self._persist_scrape_result(run, organization_id, mode, scrape_result, org_service, review_service)
        except Exception as exc:
            logger.exception("scrape failed org=%s run=%s mode=%s", organization_id, run.id, mode.value)
            self._finalize(run, ScrapeRunStatus.failed, error_code="unexpected", error_message=str(exc))
            org_service.update_scrape_status(organization_id, _mode_platform(mode), OrganizationScrapeStatus.failed)

    def _persist_scrape_result(
        self,
        run: ScrapeRun,
        organization_id: UUID,
        mode: ScrapeMode,
        result: ScrapeResult,
        org_service: OrganizationService,
        review_service: ReviewService,
    ) -> None:
        if result.needs_manual_action:
            run.debug_screenshot_path = result.debug_screenshot
            run.debug_html_path = result.debug_html
            self._finalize(
                run,
                ScrapeRunStatus.needs_manual_action,
                error_code=result.error_code or "needs_manual_action",
                error_message=result.error_message or "Manual action required",
            )
            org_service.update_scrape_status(
                organization_id, _mode_platform(mode), OrganizationScrapeStatus.needs_manual_action
            )
            return

        if result.error_code:
            run.debug_screenshot_path = result.debug_screenshot
            run.debug_html_path = result.debug_html
            self._finalize(
                run,
                ScrapeRunStatus.failed,
                error_code=result.error_code,
                error_message=result.error_message,
            )
            org_service.update_scrape_status(organization_id, _mode_platform(mode), OrganizationScrapeStatus.failed)
            return

        seen, inserted, updated = review_service.upsert_reviews(organization_id, result.reviews, mode)
        run.reviews_seen = seen
        run.reviews_inserted = inserted
        run.reviews_updated = updated
        run.status = ScrapeRunStatus.success
        run.finished_at = datetime.now(timezone.utc)
        self.db.commit()

        org_service.update_scrape_status(
            organization_id,
            _mode_platform(mode),
            OrganizationScrapeStatus.success,
            name=result.organization.name,
            rating=result.organization.rating,
            review_count=result.organization.review_count or (seen if seen else None),
            rating_count=result.organization.rating_count,
            address=result.organization.address,
            mark_success=True,
        )

        # Capture a daily rating snapshot for period-over-period deltas (feature 009).
        # Additive + best-effort: a snapshot failure must never fail the scrape.
        try:
            platform = ReviewPlatform.gis2 if mode == ScrapeMode.twogis_api else ReviewPlatform.yandex
            DashboardService(self.db).capture_snapshot(organization_id, platform)
        except Exception:  # noqa: BLE001 - snapshot is non-critical telemetry
            logger.warning("snapshot capture failed org=%s run=%s", organization_id, run.id, exc_info=True)
            self.db.rollback()

    def _finalize(
        self,
        run: ScrapeRun,
        status: ScrapeRunStatus,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        run.status = status
        run.error_code = error_code
        run.error_message = error_message
        run.finished_at = datetime.now(timezone.utc)
        self.db.commit()

    def _get_or_create_session_record(self) -> ScraperSession:
        session = self.db.query(ScraperSession).filter(ScraperSession.provider == "yandex").first()
        if not session:
            session = ScraperSession(
                provider="yandex",
                storage_state_path=settings.yandex_storage_state_path,
                status=SessionStatus.missing,
            )
            self.db.add(session)
            self.db.commit()
            self.db.refresh(session)
        return session

    def get_session_status(self) -> ScraperSession:
        session = self._get_or_create_session_record()
        # A background login/check is in flight: file heuristics must not clobber it.
        if session.status == SessionStatus.pending:
            return session
        path = Path(session.storage_state_path)
        if not path.exists():
            session.status = SessionStatus.missing
        elif path.stat().st_size > 0:
            session.status = SessionStatus.valid
        self.db.commit()
        return session

    def get_session_record(self) -> ScraperSession:
        """Current session row without the file-heuristic status refresh."""
        return self._get_or_create_session_record()

    def mark_session_pending(self) -> ScraperSession:
        session = self._get_or_create_session_record()
        session.status = SessionStatus.pending
        self.db.commit()
        return session

    def login_operator(self) -> tuple[SessionStatus, str]:
        session = self._get_or_create_session_record()
        try:
            status, message = self.auth_scraper.login(
                settings.yandex_operator_login,
                settings.yandex_operator_password,
                session.storage_state_path,
            )
        except Exception as exc:  # pending must always reach a terminal state
            logger.exception("operator login failed")
            status, message = SessionStatus.needs_manual_action, f"Login failed: {exc}"
        session.status = status
        if status == SessionStatus.valid:
            session.last_login_at = datetime.now(timezone.utc)
        session.last_checked_at = datetime.now(timezone.utc)
        self.db.commit()
        return status, message

    def check_session(self) -> ScraperSession:
        session = self._get_or_create_session_record()
        try:
            status = self.auth_scraper.check_session(session.storage_state_path)
        except Exception:  # pending must always reach a terminal state
            logger.exception("session check failed")
            status = SessionStatus.expired
        session.status = status
        session.last_checked_at = datetime.now(timezone.utc)
        self.db.commit()
        return session
