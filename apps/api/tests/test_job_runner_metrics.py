from datetime import datetime, timedelta, timezone

import pytest

from app.models.enums import (
    JobItemStatus,
    JobKind,
    JobRunStatus,
    JobTrigger,
    ReviewPlatform,
)
from app.models.job import Job
from app.models.job_run_item import JobRunItem
from app.models.organization import Organization
from app.services.job_service import JobService
from app.services.job_runner import JobRunner
from app.services.metrics_service import MetricsOutcome, MetricsResult


class FakeMetricsService:
    """Отдаёт заранее заданные исходы по порядку обхода организаций.

    Элемент списка может быть исключением (классом или инстансом) — тогда
    вызов для соответствующей организации бросает его вместо возврата
    результата.
    """

    def __init__(self, outcomes: list[MetricsResult]):
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, str]] = []

    def refresh_organization(self, org, platform):
        self.calls.append((org.name, platform))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException) or (
            isinstance(outcome, type) and issubclass(outcome, BaseException)
        ):
            raise outcome
        return outcome


@pytest.fixture()
def metrics_job(db_session):
    job = Job(kind=JobKind.org_metrics, platform=ReviewPlatform.yandex, options={"delay_seconds": 0})
    db_session.add(job)
    db_session.commit()
    return job


def _orgs(db_session, count: int, *, yandex=True):
    orgs = []
    for i in range(count):
        org = Organization(
            name=f"Org {i}",
            yandex_url=f"https://yandex.ru/maps/org/{i}" if yandex else None,
        )
        db_session.add(org)
        orgs.append(org)
    db_session.commit()
    return orgs


def test_metrics_run_writes_one_item_per_organization(db_session, metrics_job):
    _orgs(db_session, 2)
    fake = FakeMetricsService([
        MetricsResult(MetricsOutcome.updated, {"rating_after": 4.7}),
        MetricsResult(MetricsOutcome.failed, {}, "http_500"),
    ])
    run = JobService(db_session).create_run(metrics_job.id, JobTrigger.manual)

    JobRunner(db_session, metrics_service=fake, sleep=lambda _s: None).execute(run.id)

    db_session.refresh(run)
    items = db_session.query(JobRunItem).filter(JobRunItem.job_run_id == run.id).all()
    assert len(items) == 2
    assert {i.status for i in items} == {JobItemStatus.success, JobItemStatus.failed}
    assert run.status is JobRunStatus.partial
    assert (run.orgs_total, run.orgs_succeeded, run.orgs_failed) == (2, 1, 1)
    assert run.finished_at is not None


def test_metrics_run_all_failed_marks_run_failed(db_session, metrics_job):
    _orgs(db_session, 2)
    fake = FakeMetricsService([
        MetricsResult(MetricsOutcome.failed, {}, "http_500"),
        MetricsResult(MetricsOutcome.failed, {}, "http_500"),
    ])
    run = JobService(db_session).create_run(metrics_job.id, JobTrigger.manual)

    JobRunner(db_session, metrics_service=fake, sleep=lambda _s: None).execute(run.id)

    db_session.refresh(run)
    assert run.status is JobRunStatus.failed


def test_metrics_run_manual_action_without_success(db_session, metrics_job):
    _orgs(db_session, 1)
    fake = FakeMetricsService([MetricsResult(MetricsOutcome.manual_action, {}, "captcha")])
    run = JobService(db_session).create_run(metrics_job.id, JobTrigger.manual)

    JobRunner(db_session, metrics_service=fake, sleep=lambda _s: None).execute(run.id)

    db_session.refresh(run)
    assert run.status is JobRunStatus.needs_manual_action


def test_metrics_run_without_organizations_is_success(db_session, metrics_job):
    _orgs(db_session, 1, yandex=False)  # нет yandex_url — организация вне выборки
    run = JobService(db_session).create_run(metrics_job.id, JobTrigger.manual)

    JobRunner(db_session, metrics_service=FakeMetricsService([]), sleep=lambda _s: None).execute(run.id)

    db_session.refresh(run)
    assert run.status is JobRunStatus.success
    assert run.orgs_total == 0


# --- Finding 2: failure isolation coverage ------------------------------------


def test_one_organization_raising_is_isolated_others_still_processed(db_session, metrics_job):
    orgs = _orgs(db_session, 3)
    fake = FakeMetricsService([
        MetricsResult(MetricsOutcome.updated, {"rating_after": 4.7}),
        RuntimeError("scraper blew up"),
        MetricsResult(MetricsOutcome.updated, {"rating_after": 4.9}),
    ])
    run = JobService(db_session).create_run(metrics_job.id, JobTrigger.manual)

    JobRunner(db_session, metrics_service=fake, sleep=lambda _s: None).execute(run.id)

    db_session.refresh(run)
    items = {
        i.organization_id: i
        for i in db_session.query(JobRunItem).filter(JobRunItem.job_run_id == run.id).all()
    }
    # _select_organizations tie-breaks equal created_at by id, so the actual
    # processing order isn't insertion order — read it from the fake's call
    # log to know which org corresponds to which scripted outcome.
    processed_names = [name for name, _platform in fake.calls]
    orgs_by_name = {o.name: o for o in orgs}
    org_ok1 = orgs_by_name[processed_names[0]]
    org_raising = orgs_by_name[processed_names[1]]
    org_ok2 = orgs_by_name[processed_names[2]]

    # Ровно один JobRunItem на организацию, включая упавшую.
    assert len(items) == 3
    assert items[org_ok1.id].status is JobItemStatus.success
    failed_item = items[org_raising.id]
    assert failed_item.status is JobItemStatus.failed
    assert failed_item.error_code == "RuntimeError"
    assert failed_item.error_message == "scraper blew up"
    assert items[org_ok2.id].status is JobItemStatus.success

    assert run.status is JobRunStatus.partial
    assert (run.orgs_total, run.orgs_succeeded, run.orgs_failed) == (3, 2, 1)
    assert run.finished_at is not None


def test_commit_failure_for_one_organization_is_isolated_and_persists_error(
    db_session, metrics_job, monkeypatch
):
    orgs = _orgs(db_session, 2)
    fake = FakeMetricsService([
        MetricsResult(MetricsOutcome.updated, {"rating_after": 4.7}),
        MetricsResult(MetricsOutcome.updated, {"rating_after": 4.8}),
    ])
    run = JobService(db_session).create_run(metrics_job.id, JobTrigger.manual)

    real_commit = db_session.commit
    calls = {"n": 0}

    def flaky_commit():
        calls["n"] += 1
        # Порядок коммитов в execute(): 1) run.status=running, 2) orgs_total,
        # 3) первый JobRunItem. Валим ровно этот, дальнейшие — как обычно.
        if calls["n"] == 3:
            raise RuntimeError("connection dropped")
        return real_commit()

    monkeypatch.setattr(db_session, "commit", flaky_commit)

    JobRunner(db_session, metrics_service=fake, sleep=lambda _s: None).execute(run.id)

    db_session.refresh(run)
    items = db_session.query(JobRunItem).filter(JobRunItem.job_run_id == run.id).all()

    # _select_organizations tie-breaks equal created_at by id, so the actual
    # processing order isn't insertion order — read it from the fake's call
    # log instead of assuming which org went first.
    processed_names = [name for name, _platform in fake.calls]
    orgs_by_name = {o.name: o for o in orgs}
    failed_org = orgs_by_name[processed_names[0]]
    surviving_org = orgs_by_name[processed_names[1]]

    # Организация с проваленным коммитом не может получить строку — это и есть
    # тот самый невосстановимый случай; вторая организация всё же записана.
    assert len(items) == 1
    assert items[0].organization_id == surviving_org.id

    assert run.status != JobRunStatus.running
    assert run.status in (JobRunStatus.partial, JobRunStatus.failed)
    assert run.error_message is not None
    assert str(failed_org.id) in run.error_message
    assert "connection dropped" in run.error_message
    assert run.finished_at is not None


# --- Finding 3: sleep pacing and ordering --------------------------------------


def test_sleep_called_between_organizations_but_not_before_first(db_session, metrics_job):
    _orgs(db_session, 3)
    fake = FakeMetricsService([
        MetricsResult(MetricsOutcome.updated, {}),
        MetricsResult(MetricsOutcome.updated, {}),
        MetricsResult(MetricsOutcome.updated, {}),
    ])
    sleep_calls: list[float] = []
    run = JobService(db_session).create_run(metrics_job.id, JobTrigger.manual)

    JobRunner(db_session, metrics_service=fake, sleep=sleep_calls.append).execute(run.id)

    # 3 организации -> ровно 2 паузы (между 1-2 и 2-3), не перед первой.
    assert len(sleep_calls) == 2


def test_select_organizations_orders_by_created_at_then_id(db_session):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    org_later = Organization(
        name="Later",
        yandex_url="https://yandex.ru/maps/org/later",
        created_at=base + timedelta(days=1),
    )
    org_tie_a = Organization(
        name="TieA", yandex_url="https://yandex.ru/maps/org/tie-a", created_at=base
    )
    org_tie_b = Organization(
        name="TieB", yandex_url="https://yandex.ru/maps/org/tie-b", created_at=base
    )
    db_session.add_all([org_later, org_tie_a, org_tie_b])
    db_session.commit()

    result = JobRunner(db_session)._select_organizations("yandex")

    assert len(result) == 3
    # Одинаковый created_at -> тай-брейк по id; более поздний created_at идёт
    # последним.
    assert [o.id for o in result[:2]] == sorted([org_tie_a.id, org_tie_b.id])
    assert result[2].id == org_later.id


# --- Finding 4: status aggregation with skipped items (lock-in, no logic change) ---


def test_finalize_all_failed_with_some_skipped_is_failed(db_session, metrics_job):
    run = JobService(db_session).create_run(metrics_job.id, JobTrigger.manual)
    db_session.refresh(run)

    JobRunner(db_session)._finalize(
        run, [JobItemStatus.skipped, JobItemStatus.failed, JobItemStatus.failed]
    )

    assert run.status is JobRunStatus.failed


def test_finalize_success_with_some_skipped_is_success(db_session, metrics_job):
    run = JobService(db_session).create_run(metrics_job.id, JobTrigger.manual)
    db_session.refresh(run)

    JobRunner(db_session)._finalize(run, [JobItemStatus.skipped, JobItemStatus.success])

    assert run.status is JobRunStatus.success
