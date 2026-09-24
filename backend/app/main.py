import logging
from contextlib import asynccontextmanager
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import feed, ingest, storage
from .config import FETCH_INTERVAL_SECONDS, FRONTEND_ORIGIN
from .discussion import fetch_discussion
from .fetchers import SourceError
from .sources import public_sources
from .topics import TOPICS_BY_ID, public_topics
from .trends import WINDOWS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("api")

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    # First run starts immediately (in the background, so the API is up
    # straight away and the frontend can show "fetching…").
    scheduler.add_job(
        ingest.run_cycle,
        "interval",
        seconds=FETCH_INTERVAL_SECONDS,
        id="fetch_all",
        next_run_time=datetime.now(),
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Patch Notes", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SourceError)
def handle_source_error(request: Request, exc: SourceError):
    log.warning("upstream error on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=502, content={"detail": "That source isn't responding right now."})


@app.get("/api/meta")
def get_meta():
    return {"sources": public_sources(), "topics": public_topics(), "trend_windows": list(WINDOWS)}


@app.get("/api/status")
def get_status():
    return feed.get_status()


@app.post("/api/refresh")
def refresh():
    if ingest.is_running():
        return {"status": "already-running"}
    scheduler.add_job(ingest.run_cycle, id="manual_refresh", replace_existing=True)
    return {"status": "started"}


@app.get("/api/feed")
def get_feed(
    view: str = "foryou",
    topic: str | None = None,
    source: str | None = None,
    q: str | None = None,
    limit: int = 30,
    offset: int = 0,
    hours: float | None = None,
):
    if view not in ("foryou", "top", "latest"):
        raise HTTPException(status_code=400, detail=f"Unknown view '{view}'")
    if topic and topic not in TOPICS_BY_ID:
        raise HTTPException(status_code=400, detail=f"Unknown topic '{topic}'")
    if source and not feed.source_known(source):
        raise HTTPException(status_code=400, detail=f"Unknown source '{source}'")
    limit = max(1, min(limit, 100))
    return feed.get_feed(view, topic, source, (q or "").strip() or None, limit, max(0, offset), hours)


@app.get("/api/clusters/{cluster_id}")
def get_cluster(cluster_id: str):
    cluster = feed.get_cluster(cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail="Story not found")
    return cluster


@app.get("/api/stories/{story_id}/discussion")
def get_discussion(story_id: str):
    story = storage.get_story(story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")
    if story["source"] not in ("hn", "lobsters"):
        raise HTTPException(status_code=400, detail="Only Hacker News and Lobsters stories have threads.")
    return fetch_discussion(story)


class InteractionRequest(BaseModel):
    story_id: str
    action: str


@app.post("/api/interactions")
def add_interaction(body: InteractionRequest):
    if storage.get_story(body.story_id) is None:
        raise HTTPException(status_code=404, detail="Story not found")
    try:
        storage.record_interaction(body.story_id, body.action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if body.action == "save":
        storage.save_story(body.story_id)
    return {"status": "ok"}


@app.post("/api/interactions/{story_id}/undo")
def undo_interaction(story_id: str):
    undone = storage.undo_last_interaction(story_id)
    if undone is None:
        raise HTTPException(status_code=404, detail="Nothing to undo for that story")
    return {"status": "ok", "undone": undone}


@app.get("/api/saved")
def get_saved():
    saved = storage.saved_ids()
    stories = storage.get_stories(list(saved))
    actions = storage.story_actions()
    out = [feed.story_out(s, saved, actions) | {"saved_at": saved[s["id"]]} for s in stories]
    return sorted(out, key=lambda s: s["saved_at"], reverse=True)


@app.put("/api/saved/{story_id}")
def save(story_id: str):
    if storage.get_story(story_id) is None:
        raise HTTPException(status_code=404, detail="Story not found")
    storage.record_interaction(story_id, "save")
    storage.save_story(story_id)
    return {"status": "ok"}


@app.delete("/api/saved/{story_id}")
def unsave(story_id: str):
    storage.unsave_story(story_id)
    return {"status": "ok"}


@app.get("/api/catchup")
def get_catchup(limit: int = 30):
    return feed.get_catchup(max(1, min(limit, 100)))


@app.get("/api/profile")
def get_profile():
    return feed.get_profile()


class PrefsRequest(BaseModel):
    followed_topics: list[str] | None = None
    muted_terms: list[str] | None = None
    muted_sources: list[str] | None = None


@app.get("/api/prefs")
def get_prefs():
    return storage.get_prefs()


@app.put("/api/prefs")
def put_prefs(body: PrefsRequest):
    updates = body.model_dump(exclude_none=True)
    for topic in updates.get("followed_topics", []):
        if topic not in TOPICS_BY_ID:
            raise HTTPException(status_code=400, detail=f"Unknown topic '{topic}'")
    for source in updates.get("muted_sources", []):
        if not feed.source_known(source):
            raise HTTPException(status_code=400, detail=f"Unknown source '{source}'")
    if "muted_terms" in updates:
        updates["muted_terms"] = sorted({t.strip() for t in updates["muted_terms"] if t.strip()}, key=str.lower)
    return storage.set_prefs(updates)


@app.get("/api/trends")
def get_trends(window: str = "24h"):
    if window not in WINDOWS:
        raise HTTPException(status_code=400, detail=f"Unknown window '{window}'")
    return feed.get_trends(window)


@app.get("/api/quiz")
def get_quiz(round: int = 1):
    return feed.get_quiz(max(1, round))


class QuizResultRequest(BaseModel):
    quiz_id: str
    score: int
    total: int


@app.post("/api/quiz/results")
def add_quiz_result(body: QuizResultRequest):
    if body.total <= 0 or not 0 <= body.score <= body.total:
        raise HTTPException(status_code=400, detail="Score must be between 0 and the number of questions.")
    return storage.record_quiz_result(body.quiz_id, body.score, body.total)


@app.get("/api/quiz/results")
def list_quiz_results(limit: int = 20):
    return storage.list_quiz_results(limit)
