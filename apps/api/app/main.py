from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import organizations, reviews, scrape_runs, scraper_sessions
from app.core.config import settings

app = FastAPI(title="Yandex Reviews API", version="0.1.0")

origins = [origin.strip() for origin in settings.api_cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(organizations.router)
app.include_router(reviews.router)
app.include_router(scrape_runs.router)
app.include_router(scraper_sessions.router)
