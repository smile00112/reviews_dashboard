from uuid import UUID

from sqlalchemy.orm import Session

from app.models.enums import OrganizationScrapeStatus, ScrapeMode
from app.models.organization import Organization
from app.schemas.organization import OrganizationCreate, OrganizationUpdate
from app.services.url_utils import extract_external_id, normalize_yandex_url, validate_yandex_url


class OrganizationService:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[Organization]:
        return self.db.query(Organization).order_by(Organization.created_at.desc()).all()

    def get(self, organization_id: UUID) -> Organization | None:
        return self.db.query(Organization).filter(Organization.id == organization_id).first()

    def create(self, data: OrganizationCreate) -> Organization:
        validate_yandex_url(data.yandex_url)
        normalized = normalize_yandex_url(data.yandex_url)
        org = Organization(
            yandex_url=data.yandex_url.strip(),
            normalized_url=normalized,
            external_id=extract_external_id(normalized),
            preferred_scrape_mode=data.preferred_scrape_mode,
            last_scrape_status=OrganizationScrapeStatus.pending,
        )
        self.db.add(org)
        self.db.commit()
        self.db.refresh(org)
        return org

    def update(self, organization_id: UUID, data: OrganizationUpdate) -> Organization | None:
        org = self.get(organization_id)
        if not org:
            return None
        if data.preferred_scrape_mode is not None:
            org.preferred_scrape_mode = data.preferred_scrape_mode
        if data.name is not None:
            org.name = data.name
        self.db.commit()
        self.db.refresh(org)
        return org

    def delete(self, organization_id: UUID) -> bool:
        org = self.get(organization_id)
        if not org:
            return False
        self.db.delete(org)
        self.db.commit()
        return True

    def list_ids(self) -> list[UUID]:
        return [row[0] for row in self.db.query(Organization.id).all()]

    def update_scrape_status(
        self,
        organization_id: UUID,
        status: OrganizationScrapeStatus,
        *,
        name: str | None = None,
        rating: float | None = None,
        review_count: int | None = None,
        address: str | None = None,
        mark_success: bool = False,
    ) -> None:
        org = self.get(organization_id)
        if not org:
            return
        org.last_scrape_status = status
        if name:
            org.name = name
        if rating is not None:
            org.rating = rating
        if review_count is not None:
            org.review_count = review_count
        if address:
            org.address = address
        if mark_success:
            from datetime import datetime, timezone

            org.last_successful_scrape_at = datetime.now(timezone.utc)
        self.db.commit()
