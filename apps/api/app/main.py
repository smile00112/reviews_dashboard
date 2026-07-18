import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.admin import setup_admin
from app.api import auth, companies, dashboard, jobs, organizations, reviews, scrape_runs, scraper_sessions
from app.core.config import settings
from app.core.database import engine
from app.core.logging import setup_logging
from app.services.job_scheduler import scheduler as job_scheduler

setup_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.jobs_scheduler_enabled:
        try:
            job_scheduler.start()
        except Exception:
            # A bad Job row (cron that bypassed validation) or a briefly
            # unreachable DB must not take the whole API down with it — the
            # read-only dashboard has nothing to do with the scheduler.
            # Leave it off; surface loudly so this doesn't go unnoticed.
            logger.error("job scheduler failed to start; continuing without it", exc_info=True)
    try:
        yield
    finally:
        job_scheduler.shutdown()


app = FastAPI(title="Yandex Reviews API", version="0.1.0", lifespan=lifespan)


def _cors_origins(raw: str) -> list[str]:
    """Fail closed: with allow_credentials=True a '*' fallback is a misconfiguration
    browsers reject anyway — an empty origin list must abort startup, not widen."""
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if not origins:
        raise RuntimeError(
            "API_CORS_ORIGINS must list at least one origin; refusing to fall back to '*'"
        )
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(settings.api_cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.admin_secret_key,
    max_age=settings.session_max_age,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


setup_admin(app, engine)

app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(organizations.router)
app.include_router(reviews.router)
app.include_router(scrape_runs.router)
app.include_router(scraper_sessions.router)
app.include_router(dashboard.router)
app.include_router(jobs.router)
