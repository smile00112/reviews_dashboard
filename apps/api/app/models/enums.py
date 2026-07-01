import enum


class ScrapeMode(str, enum.Enum):
    public = "public"
    operator_auth = "operator_auth"
    public_http = "public_http"
    scrapeops = "scrapeops"


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
