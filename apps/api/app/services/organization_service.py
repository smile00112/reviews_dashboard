from uuid import UUID

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.enums import OrganizationScrapeStatus, ScrapeMode
from app.models.organization import Organization
from app.schemas.organization import OrganizationCreate, OrganizationUpdate
from app.services.url_utils import extract_external_id, normalize_yandex_url, validate_yandex_url


# Operator-editable multi-platform metric fields shared by create/update.
_PLATFORM_FIELDS = (
    "yandex_rating_count",
    "gis2_url",
    "gis2_rating",
    "gis2_review_count",
    "gis2_rating_count",
    "google_url",
    "google_rating",
    "google_review_count",
    "google_rating_count",
)

# platform -> (status col, success-timestamp col, rating col, review_count col, rating_count col)
_PLATFORM_STATUS_COLUMNS = {
    "yandex": (
        "yandex_scrape_status",
        "yandex_last_successful_scrape_at",
        "rating",
        "review_count",
        "yandex_rating_count",
    ),
    "2gis": (
        "gis2_scrape_status",
        "gis2_last_successful_scrape_at",
        "gis2_rating",
        "gis2_review_count",
        "gis2_rating_count",
    ),
}


class OrganizationService:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self, company_id: UUID | None = None) -> list[Organization]:
        query = self.db.query(Organization)
        if company_id is not None:
            query = query.filter(Organization.company_id == company_id)
        return query.order_by(Organization.created_at.desc()).all()

    def _validate_company(self, company_id: UUID | None) -> None:
        if company_id is None:
            return
        if not self.db.query(Company.id).filter(Company.id == company_id).first():
            raise ValueError("Company not found")

    def get(self, organization_id: UUID) -> Organization | None:
        return self.db.query(Organization).filter(Organization.id == organization_id).first()

    def create(self, data: OrganizationCreate) -> Organization:
        validate_yandex_url(data.yandex_url)
        self._validate_company(data.company_id)
        normalized = normalize_yandex_url(data.yandex_url)
        org = Organization(
            yandex_url=data.yandex_url.strip(),
            normalized_url=normalized,
            external_id=extract_external_id(normalized),
            preferred_scrape_mode=data.preferred_scrape_mode,
            name=data.name,
            city=data.city,
            region=data.region,
            address=data.address,
            company_id=data.company_id,
        )
        for field in _PLATFORM_FIELDS:
            setattr(org, field, getattr(data, field))
        self.db.add(org)
        self.db.commit()
        self.db.refresh(org)
        return org

    def update(self, organization_id: UUID, data: OrganizationUpdate) -> Organization | None:
        org = self.get(organization_id)
        if not org:
            return None
        fields_set = data.model_fields_set
        if data.preferred_scrape_mode is not None:
            org.preferred_scrape_mode = data.preferred_scrape_mode
        if data.name is not None:
            org.name = data.name
        # city/region/address/company_id honor explicit values (incl. clearing to null).
        if "city" in fields_set:
            org.city = data.city
        if "region" in fields_set:
            org.region = data.region
        if "address" in fields_set:
            org.address = data.address
        if "company_id" in fields_set:
            self._validate_company(data.company_id)
            org.company_id = data.company_id
        # Platform metrics honor explicit values (incl. clearing to null).
        for field in _PLATFORM_FIELDS:
            if field in fields_set:
                setattr(org, field, getattr(data, field))
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
        platform: str,
        status: OrganizationScrapeStatus,
        *,
        name: str | None = None,
        rating: float | None = None,
        review_count: int | None = None,
        rating_count: int | None = None,
        address: str | None = None,
        mark_success: bool = False,
    ) -> None:
        """Update one platform's scrape status (+ metrics) on an org. `platform` is
        'yandex' or '2gis'; each writes only its own columns."""
        org = self.get(organization_id)
        if not org:
            return
        status_col, ts_col, rating_col, count_col, rating_count_col = _PLATFORM_STATUS_COLUMNS[platform]
        setattr(org, status_col, status)
        if name:
            org.name = name
        if address:
            org.address = address
        if rating is not None:
            setattr(org, rating_col, rating)
        if review_count is not None:
            setattr(org, count_col, review_count)
        if rating_count is not None:
            setattr(org, rating_count_col, rating_count)
        if mark_success:
            from datetime import datetime, timezone

            setattr(org, ts_col, datetime.now(timezone.utc))
        self.db.commit()
