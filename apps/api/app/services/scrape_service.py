from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import OrganizationScrapeStatus, ScrapeMode, ScrapeRunStatus, SessionStatus
from app.models.scrape_run import ScrapeRun
from app.models.scraper_session import ScraperSession
from app.scraper.types import ScrapeResult
from app.scraper.yandex_auth import YandexAuthScraper
from app.scraper.yandex_http import YandexHttpScraper
from app.scraper.yandex_public import YandexPublicScraper
from app.scraper.yandex_scrapeops import YandexScrapeOpsScraper
from app.services.organization_service import OrganizationService
from app.services.review_service import ReviewService


class ScrapeService:
    def __init__(
        self,
        db: Session,
        public_scraper: YandexPublicScraper | None = None,
        http_scraper: YandexHttpScraper | None = None,
        scrapeops_scraper: YandexScrapeOpsScraper | None = None,
    ):
        self.db = db
        self.public_scraper = public_scraper or YandexPublicScraper()
        self.http_scraper = http_scraper or YandexHttpScraper()
        self.auth_scraper = YandexAuthScraper()
        self.scrapeops_scraper = scrapeops_scraper or YandexScrapeOpsScraper()

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

    def execute_run(self, run_id: UUID) -> None:
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
            org_service.update_scrape_status(org.id, OrganizationScrapeStatus.running)
            self._scrape_organization(run, org.yandex_url, org.id, run.mode, org_service, review_service)
            return

        org_ids = org_service.list_ids()
        for org_id in org_ids:
            org = org_service.get(org_id)
            if not org:
                continue
            child = ScrapeRun(organization_id=org_id, mode=run.mode, status=ScrapeRunStatus.running)
            self.db.add(child)
            self.db.commit()
            self.db.refresh(child)
            self._scrape_organization(child, org.yandex_url, org.id, run.mode, org_service, review_service)

        run.status = ScrapeRunStatus.success
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
    ) -> None:
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
                    org_service.update_scrape_status(organization_id, OrganizationScrapeStatus.needs_manual_action)
                    return
                scrape_result = self.auth_scraper.scrape(url, session.storage_state_path)
            elif mode == ScrapeMode.public_http:
                scrape_result = self.http_scraper.scrape(url)
            elif mode == ScrapeMode.scrapeops:
                scrape_result = self.scrapeops_scraper.scrape(url)
            else:
                scrape_result = self.public_scraper.scrape(url)

            self._persist_scrape_result(run, organization_id, mode, scrape_result, org_service, review_service)
        except Exception as exc:
            self._finalize(run, ScrapeRunStatus.failed, error_code="unexpected", error_message=str(exc))
            org_service.update_scrape_status(organization_id, OrganizationScrapeStatus.failed)

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
            org_service.update_scrape_status(organization_id, OrganizationScrapeStatus.needs_manual_action)
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
            org_service.update_scrape_status(organization_id, OrganizationScrapeStatus.failed)
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
            OrganizationScrapeStatus.success,
            name=result.organization.name,
            rating=result.organization.rating,
            review_count=result.organization.review_count or (seen if seen else None),
            address=result.organization.address,
            mark_success=True,
        )

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
        path = Path(session.storage_state_path)
        if not path.exists():
            session.status = SessionStatus.missing
        elif path.stat().st_size > 0:
            session.status = SessionStatus.valid
        self.db.commit()
        return session

    def login_operator(self) -> tuple[SessionStatus, str]:
        session = self._get_or_create_session_record()
        status, message = self.auth_scraper.login(
            settings.yandex_operator_login,
            settings.yandex_operator_password,
            session.storage_state_path,
        )
        session.status = status
        if status == SessionStatus.valid:
            session.last_login_at = datetime.now(timezone.utc)
        session.last_checked_at = datetime.now(timezone.utc)
        self.db.commit()
        return status, message

    def check_session(self) -> ScraperSession:
        session = self._get_or_create_session_record()
        status = self.auth_scraper.check_session(session.storage_state_path)
        session.status = status
        session.last_checked_at = datetime.now(timezone.utc)
        self.db.commit()
        return session
