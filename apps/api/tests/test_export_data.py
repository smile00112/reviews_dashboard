import json
from datetime import date, datetime, timezone
from uuid import uuid4

from app.models.company import Company
from app.models.enums import OrganizationScrapeStatus, ScrapeMode
from app.models.organization import Organization
from app.models.review import Review
from scripts.export_data import (
    COMPANY_FIELDS,
    ORGANIZATION_FIELDS,
    REVIEW_FIELDS,
    export_companies,
    export_organizations,
    export_reviews,
    serialize_row,
)


def test_serialize_row_coerces_uuid_datetime_decimal():
    company = Company(id=uuid4(), name="Acme", is_active=True)
    company.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    company.updated_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    row = serialize_row(company, COMPANY_FIELDS)
    assert row["id"] == str(company.id)
    assert row["created_at"] == "2026-01-01T00:00:00+00:00"
    # JSON-round-trippable
    json.dumps(row)


def test_export_companies_writes_one_line_per_row(db_session, tmp_path):
    db_session.add_all([Company(name="Acme"), Company(name="Beta")])
    db_session.commit()

    out_path = tmp_path / "companies.jsonl"
    count = export_companies(db_session, out_path)

    assert count == 2
    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    names = {json.loads(line)["name"] for line in lines}
    assert names == {"Acme", "Beta"}


def test_export_organizations_includes_enum_and_platform_fields(db_session, tmp_path):
    org = Organization(
        name="Point 1",
        yandex_url="https://yandex.ru/maps/org/x/1/",
        normalized_url="https://yandex.ru/maps/org/x/1",
        external_id="1",
        rating=4.5,
        preferred_scrape_mode=ScrapeMode.public,
        yandex_scrape_status=OrganizationScrapeStatus.success,
    )
    db_session.add(org)
    db_session.commit()

    out_path = tmp_path / "organizations.jsonl"
    count = export_organizations(db_session, out_path)

    assert count == 1
    row = json.loads(out_path.read_text(encoding="utf-8").strip())
    assert row["preferred_scrape_mode"] == "public"
    assert row["yandex_scrape_status"] == "success"
    assert row["rating"] == 4.5
    assert set(ORGANIZATION_FIELDS) == set(row.keys())


def test_export_reviews_streams_all_rows(db_session, tmp_path):
    org = Organization(name="Point 1")
    db_session.add(org)
    db_session.commit()
    db_session.add(
        Review(
            organization_id=org.id,
            scrape_mode=ScrapeMode.public,
            rating=5,
            review_text="Great",
            content_hash="hash1",
            review_date=date(2026, 1, 1),
        )
    )
    db_session.commit()

    out_path = tmp_path / "reviews.jsonl"
    count = export_reviews(db_session, out_path)

    assert count == 1
    row = json.loads(out_path.read_text(encoding="utf-8").strip())
    assert row["review_text"] == "Great"
    assert row["review_date"] == "2026-01-01"
    assert "paid_marked_by_user_id" not in row
    assert "replied_by_user_id" not in row
    assert set(REVIEW_FIELDS) == set(row.keys())
