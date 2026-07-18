import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    review_operator = "review_operator"


class ReviewStatus(str, enum.Enum):
    new = "new"
    in_progress = "in_progress"
    answered = "answered"
    escalated = "escalated"


class ReviewPlatform(str, enum.Enum):
    yandex = "yandex"
    google = "google"
    gis2 = "gis2"


class ScrapeMode(str, enum.Enum):
    public = "public"
    operator_auth = "operator_auth"
    public_http = "public_http"
    scrapeops = "scrapeops"
    twogis_api = "twogis_api"


class OrganizationScrapeStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    needs_manual_action = "needs_manual_action"


class ScrapeRunStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    success = "success"
    failed = "failed"
    needs_manual_action = "needs_manual_action"


class SessionStatus(str, enum.Enum):
    missing = "missing"
    valid = "valid"
    expired = "expired"
    needs_manual_action = "needs_manual_action"
    # Background login/check scheduled but not finished (feature 010).
    pending = "pending"


class JobKind(str, enum.Enum):
    org_metrics = "org_metrics"
    reviews = "reviews"


class JobTrigger(str, enum.Enum):
    schedule = "schedule"
    manual = "manual"


class JobRunStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    success = "success"
    # Часть организаций отработала, часть упала — не failed и не success.
    partial = "partial"
    failed = "failed"
    needs_manual_action = "needs_manual_action"
    cancelled = "cancelled"


class JobItemStatus(str, enum.Enum):
    success = "success"
    skipped = "skipped"
    failed = "failed"
    needs_manual_action = "needs_manual_action"
