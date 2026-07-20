"""Loading Sprav weekly ratings into rating_snapshot.

Contracts worth pinning: a week without a rating is a gap (never a zero row),
review_count stays NULL because the cabinet publishes none, the load is
idempotent, and --dry-run writes nothing.
"""

from datetime import date
from decimal import Decimal

from app.models.enums import ReviewPlatform
from app.models.organization import Organization
from app.models.rating_snapshot import RatingSnapshot
from scripts.load_rating_snapshots import run


def _org(db, name="Пермь-07 Солдатова 28"):
    org = Organization(name=name)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _record(org, history, *, method="external_id", confidence=1.0):
    return {
        "org_id": str(org.id),
        "match_method": method,
        "match_confidence": confidence,
        "history": history,
    }


def _week(week, rating):
    return {"week": week, "rating": rating}


def test_writes_one_row_per_week(db_session):
    org = _org(db_session)
    summary = run(
        db_session,
        [_record(org, [_week("2026-07-06", 4.3), _week("2026-07-13", 4.4)])],
        min_confidence=0.0,
        dry_run=False,
    )
    rows = db_session.query(RatingSnapshot).order_by(RatingSnapshot.captured_on).all()
    assert summary.inserted == 2
    assert [r.captured_on for r in rows] == [date(2026, 7, 6), date(2026, 7, 13)]
    assert [Decimal(str(r.rating)) for r in rows] == [Decimal("4.30"), Decimal("4.40")]


def test_rows_are_written_for_the_yandex_platform(db_session):
    org = _org(db_session)
    run(db_session, [_record(org, [_week("2026-07-06", 4.3)])], min_confidence=0.0, dry_run=False)
    assert db_session.query(RatingSnapshot).one().platform == ReviewPlatform.yandex


def test_review_count_stays_null_because_the_cabinet_has_none(db_session):
    """A 0 here would be a real measurement; the truth is 'нет данных'."""
    org = _org(db_session)
    run(db_session, [_record(org, [_week("2026-07-06", 4.3)])], min_confidence=0.0, dry_run=False)
    assert db_session.query(RatingSnapshot).one().review_count is None


def test_week_without_a_rating_writes_no_row(db_session):
    org = _org(db_session)
    summary = run(
        db_session,
        [_record(org, [_week("2026-07-06", None), _week("2026-07-13", 4.4)])],
        min_confidence=0.0,
        dry_run=False,
    )
    assert summary.skipped["no_rating"] == 1
    assert db_session.query(RatingSnapshot).count() == 1


def test_dry_run_writes_nothing_but_still_reports(db_session):
    org = _org(db_session)
    summary = run(db_session, [_record(org, [_week("2026-07-06", 4.3)])], min_confidence=0.0, dry_run=True)
    assert summary.inserted == 1
    assert db_session.query(RatingSnapshot).count() == 0


def test_reloading_the_same_data_inserts_nothing(db_session):
    org = _org(db_session)
    records = [_record(org, [_week("2026-07-06", 4.3)])]
    run(db_session, records, min_confidence=0.0, dry_run=False)
    summary = run(db_session, records, min_confidence=0.0, dry_run=False)
    assert (summary.inserted, summary.unchanged) == (0, 1)
    assert db_session.query(RatingSnapshot).count() == 1


def test_a_changed_rating_updates_the_existing_row(db_session):
    org = _org(db_session)
    run(db_session, [_record(org, [_week("2026-07-06", 4.3)])], min_confidence=0.0, dry_run=False)
    summary = run(db_session, [_record(org, [_week("2026-07-06", 4.6)])], min_confidence=0.0, dry_run=False)
    assert summary.updated == 1
    assert Decimal(str(db_session.query(RatingSnapshot).one().rating)) == Decimal("4.60")


def test_unmatched_branch_is_skipped(db_session):
    record = {"org_id": None, "match_method": None, "history": [_week("2026-07-06", 4.3)]}
    summary = run(db_session, [record], min_confidence=0.0, dry_run=False)
    assert summary.skipped["unmatched"] == 1
    assert db_session.query(RatingSnapshot).count() == 0


def test_low_confidence_address_match_is_skipped_when_gated(db_session):
    org = _org(db_session)
    record = _record(org, [_week("2026-07-06", 4.3)], method="address", confidence=0.55)
    summary = run(db_session, [record], min_confidence=0.7, dry_run=False)
    assert summary.skipped["low_confidence"] == 1
    assert db_session.query(RatingSnapshot).count() == 0


def test_confidence_gate_does_not_apply_to_permalink_matches(db_session):
    """external_id is exact — its 1.0 is not a fallback score to be second-guessed."""
    org = _org(db_session)
    record = _record(org, [_week("2026-07-06", 4.3)], method="external_id", confidence=1.0)
    run(db_session, [record], min_confidence=0.9, dry_run=False)
    assert db_session.query(RatingSnapshot).count() == 1


def test_branch_without_history_is_skipped(db_session):
    org = _org(db_session)
    summary = run(db_session, [_record(org, [])], min_confidence=0.0, dry_run=False)
    assert summary.skipped["no_history"] == 1
