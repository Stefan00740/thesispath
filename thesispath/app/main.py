import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .database import Base, engine
from .routers import auth, milestones, notifications, stats, theses, topics
from .seed import seed_demo


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.getenv("AUTO_CREATE", "1") == "1":  # в Docker схему создаёт Alembic
        Base.metadata.create_all(engine)
    if os.getenv("SEED_DEMO") == "1":
        seed_demo()
    yield


app = FastAPI(
    title="ThesisPath",
    description="Карта пути к защите диплома: темы, этапы, версии файлов, комментарии, индекс готовности.",
    lifespan=lifespan,
)
for r in (auth.router, topics.router, theses.router, milestones.router, stats.router, notifications.router):
    app.include_router(r)

_INDEX = Path(__file__).parent / "static" / "index.html"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index():
    return _INDEX.read_text(encoding="utf-8")


@app.get("/health", tags=["System"])
def health():
    return {"status": "ok"}
