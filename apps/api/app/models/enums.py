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
