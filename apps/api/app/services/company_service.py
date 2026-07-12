from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.organization import Organization
from app.schemas.company import CompanyCreate, CompanyUpdate

UNASSIGNED_CITY = "Без города"


class CompanyService:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[Company]:
        return self.db.query(Company).order_by(Company.created_at.desc()).all()

    def get(self, company_id: UUID) -> Company | None:
        return self.db.query(Company).filter(Company.id == company_id).first()

    def create(self, data: CompanyCreate) -> Company:
        company = Company(name=data.name.strip(), is_active=data.is_active)
        self.db.add(company)
        self.db.commit()
        self.db.refresh(company)
        return company

    def update(self, company_id: UUID, data: CompanyUpdate) -> Company | None:
        company = self.get(company_id)
        if not company:
            return None
        if data.name is not None:
            company.name = data.name.strip()
        if data.is_active is not None:
            company.is_active = data.is_active
        self.db.commit()
        self.db.refresh(company)
        return company

    def delete(self, company_id: UUID) -> bool:
        company = self.get(company_id)
        if not company:
            return False
        # Detach branches (do NOT delete them or their reviews).
        self.db.query(Organization).filter(Organization.company_id == company_id).update(
            {Organization.company_id: None}, synchronize_session=False
        )
        self.db.delete(company)
        self.db.commit()
        return True

    def branch_counts(self) -> dict[UUID, int]:
        """Branch count per company in ONE grouped query (feature 010, FR-008)."""
        rows = (
            self.db.query(Organization.company_id, func.count(Organization.id))
            .filter(Organization.company_id.isnot(None))
            .group_by(Organization.company_id)
            .all()
        )
        return {company_id: count for company_id, count in rows}

    def branch_count(self, company_id: UUID) -> int:
        return (
            self.db.query(func.count(Organization.id))
            .filter(Organization.company_id == company_id)
            .scalar()
            or 0
        )

    def list_branches_grouped_by_city(self, company_id: UUID) -> list[tuple[str, list[Organization]]]:
        """Return ``[(city, [branches])]`` ordered by city, then branch name.

        NULL/empty city is bucketed under ``UNASSIGNED_CITY`` and sorted last.
        """
        branches = (
            self.db.query(Organization)
            .filter(Organization.company_id == company_id)
            .all()
        )
        groups: dict[str, list[Organization]] = {}
        for branch in branches:
            city = (branch.city or "").strip() or UNASSIGNED_CITY
            groups.setdefault(city, []).append(branch)

        def city_sort_key(city: str) -> tuple[int, str]:
            # Unassigned bucket sorts last.
            return (1, "") if city == UNASSIGNED_CITY else (0, city.casefold())

        ordered: list[tuple[str, list[Organization]]] = []
        for city in sorted(groups, key=city_sort_key):
            members = sorted(groups[city], key=lambda o: (o.name or "").casefold())
            ordered.append((city, members))
        return ordered
