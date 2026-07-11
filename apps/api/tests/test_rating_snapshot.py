"""Rating snapshot capture + delta (feature 009).

Snapshot is the additive daily history that powers period-over-period rating
deltas on the network overview. One row per (org, platform, day); same-day
capture upserts; delta is None until history covers the requested period.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.enums import ReviewPlatform
from app.models.organization import Organization
from app.models.rating_snapshot import RatingSnapshot
from app.services.dashboard_service import DashboardService


def _org(db, *, rating=4.5, review_count=100):
    org = Organization(name="Test", rating=rating, review_count=review_count)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def test_capture_writes_one_row_per_day(db_session):
    org = _org(db_session)
    now = datetime(2026, 7, 11, 9, 0, tzinfo=timezone.utc)

    DashboardService(db_session).capture_snapshot(org.id, ReviewPlatform.yandex, now=now)

    rows = db_session.query(RatingSnapshot).all()
    assert len(rows) == 1
    assert rows[0].platform == ReviewPlatform.yandex
    assert Decimal(str(rows[0].rating)) == Decimal("4.50")
    assert rows[0].review_count == 100
    assert rows[0].captured_on == now.date()


def test_same_day_capture_upserts(db_session):
    org = _org(db_session, rating=4.5)
    svc = DashboardService(db_session)
    now = datetime(2026, 7, 11, 9, 0, tzinfo=timezone.utc)

    svc.capture_snapshot(org.id, ReviewPlatform.yandex, now=now)
    # rating changes later the same day -> upsert, not a second row
    org.rating = 4.6
    db_session.commit()
    svc.capture_snapshot(org.id, ReviewPlatform.yandex, now=now + timedelta(hours=3))

    rows = db_session.query(RatingSnapshot).all()
    assert len(rows) == 1
    assert Decimal(str(rows[0].rating)) == Decimal("4.60")


def test_delta_none_without_history(db_session):
    org = _org(db_session, rating=4.5)
    period_start = (datetime.now(timezone.utc) - timedelta(days=30)).date()
    delta = DashboardService(db_session).rating_delta(org.id, ReviewPlatform.yandex, period_start)
    assert delta is None


def test_delta_uses_earliest_snapshot_in_period(db_session):
    org = _org(db_session, rating=4.5)
    svc = DashboardService(db_session)
    start = datetime(2026, 6, 11, 9, 0, tzinfo=timezone.utc)

    # Snapshot 30 days ago at 4.20
    org.rating = 4.2
    db_session.commit()
    svc.capture_snapshot(org.id, ReviewPlatform.yandex, now=start)

    # Current rating 4.50
    org.rating = 4.5
    db_session.commit()

    delta = svc.rating_delta(org.id, ReviewPlatform.yandex, start.date())
    assert delta is not None
    assert round(delta, 2) == 0.30


def test_capture_reads_platform_specific_columns(db_session):
    org = Organization(name="Multi", rating=4.5, review_count=10, gis2_rating=4.1, gis2_review_count=20)
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    now = datetime(2026, 7, 11, tzinfo=timezone.utc)

    DashboardService(db_session).capture_snapshot(org.id, ReviewPlatform.gis2, now=now)

    row = db_session.query(RatingSnapshot).filter_by(platform=ReviewPlatform.gis2).one()
    assert Decimal(str(row.rating)) == Decimal("4.10")
    assert row.review_count == 20
