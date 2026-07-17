from datetime import date

from app.models.company import Company
from app.models.enums import OrganizationScrapeStatus, ReviewStatus, ScrapeMode
from app.models.organization import Organization
from app.models.review import Review
from scripts.export_data import export_companies, export_organizations, export_reviews
from scripts.import_data import import_all


def _seed_source(db_session):
    """Populate db_session as if it were the source server, return (company, org, review)."""
    company = Company(name="Acme")
    db_session.add(company)
    db_session.commit()

    org = Organization(
        name="Point 1",
        yandex_url="https://yandex.ru/maps/org/x/1/",
        normalized_url="https://yandex.ru/maps/org/x/1",
        company_id=company.id,
        preferred_scrape_mode=ScrapeMode.public,
        yandex_scrape_status=OrganizationScrapeStatus.success,
    )
    db_session.add(org)
    db_session.commit()

    review = Review(
        organization_id=org.id,
        scrape_mode=ScrapeMode.public,
        rating=5,
        review_text="Great",
        content_hash="hash1",
        review_date=date(2026, 1, 1),
        status=ReviewStatus.new,
    )
    db_session.add(review)
    db_session.commit()
    return company, org, review


def _export_all(db_session, out_dir):
    export_companies(db_session, out_dir / "companies.jsonl")
    export_organizations(db_session, out_dir / "organizations.jsonl")
    export_reviews(db_session, out_dir / "reviews.jsonl")


def test_import_into_empty_db_reproduces_source_rows(db_session, target_db_session, tmp_path):
    company, org, review = _seed_source(db_session)
    _export_all(db_session, tmp_path)

    summary = import_all(target_db_session, tmp_path)

    assert summary == {"companies": (1, 0), "organizations": (1, 0), "reviews": (1, 0)}
    imported_org = target_db_session.query(Organization).filter(Organization.id == org.id).one()
    assert imported_org.name == "Point 1"
    assert imported_org.company_id == company.id
    imported_review = target_db_session.query(Review).filter(Review.id == review.id).one()
    assert imported_review.review_text == "Great"
    assert imported_review.status == ReviewStatus.new
    assert imported_review.paid_marked_by_user_id is None
    assert imported_review.replied_by_user_id is None


def test_reimport_updates_changed_fields_without_duplicating(db_session, target_db_session, tmp_path):
    company, org, review = _seed_source(db_session)
    _export_all(db_session, tmp_path)
    import_all(target_db_session, tmp_path)

    # Source-side edit, re-export, re-import.
    review.status = ReviewStatus.answered
    review.reply_text = "Thanks!"
    db_session.commit()
    _export_all(db_session, tmp_path)

    summary = import_all(target_db_session, tmp_path)

    assert summary == {"companies": (0, 1), "organizations": (0, 1), "reviews": (0, 1)}
    assert target_db_session.query(Review).count() == 1
    imported_review = target_db_session.query(Review).filter(Review.id == review.id).one()
    assert imported_review.status == ReviewStatus.answered
    assert imported_review.reply_text == "Thanks!"


def test_dry_run_does_not_commit(db_session, target_db_session, tmp_path):
    _seed_source(db_session)
    _export_all(db_session, tmp_path)

    summary = import_all(target_db_session, tmp_path, dry_run=True)

    assert summary == {"companies": (1, 0), "organizations": (1, 0), "reviews": (1, 0)}
    target_db_session.rollback()
    assert target_db_session.query(Company).count() == 0


def test_import_order_is_fk_safe_organizations_before_reviews_reference_company(
    db_session, target_db_session, tmp_path
):
    """organizations.jsonl references a company_id only defined in companies.jsonl;
    reviews.jsonl references an organization_id only defined in organizations.jsonl.
    Importing companies -> organizations -> reviews in that order must not FK-fail."""
    _seed_source(db_session)
    _export_all(db_session, tmp_path)

    summary = import_all(target_db_session, tmp_path)

    assert all(inserted == 1 for inserted, _ in summary.values())
