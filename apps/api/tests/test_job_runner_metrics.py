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
    """Отдаёт заранее заданные исходы по порядку обхода организаций."""

    def __init__(self, outcomes: list[MetricsResult]):
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, str]] = []

    def refresh_organization(self, org, platform):
        self.calls.append((org.name, platform))
        return self.outcomes.pop(0)


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
