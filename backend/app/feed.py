"""The read side: assemble ranked, annotated clusters for each view."""

import time
from datetime import datetime

from . import ingest, ranking, storage
from .config import FETCH_INTERVAL_SECONDS, RETENTION_DAYS
from .quiz import build_quiz
from .sources import SOURCES, SOURCES_BY_ID
from .topics import TOPICS
from .trends import WINDOWS, rising_terms, topic_volumes

DEFAULT_HOURS = 48
CATCHUP_HOURS = 36
PROFILE_LOOKBACK_DAYS = 60


def story_out(story: dict, saved: dict[str, float], actions: dict[str, set[str]]) -> dict:
    acted = actions.get(story["id"], set())
    triage = "keep" if "keep" in acted else "skip" if "skip" in acted else None
    return {
        "id": story["id"],
        "source": story["source"],
        "title": story["title"],
        "url": story["url"],
        "discussion_url": story.get("discussion_url"),
        "summary": story.get("summary") or "",
        "image": story.get("image"),
        "author": story.get("author"),
        "published_at": story["published_at"],
        "score": story.get("score"),
        "comments": story.get("comments"),
        "topics": story["topics"],
        "extra": story.get("extra") or {},
        "saved": story["id"] in saved,
        "read": "open" in acted,
        "triage": triage,
    }


def _cluster_out(cluster: dict, saved, actions) -> dict:
    return {
        "id": cluster["id"],
        "lead": story_out(cluster["lead"], saved, actions),
        "coverage": [story_out(s, saved, actions) for s in cluster["stories"] if s["id"] != cluster["lead"]["id"]],
        "sources": cluster["sources"],
        "source_count": cluster["source_count"],
        "topics": cluster["topics"],
        "first_published": cluster["first_published"],
        "last_published": cluster["last_published"],
        "discussions": cluster["discussions"],
        "reasons": cluster.get("reasons", []),
        "score": round(cluster.get("score", cluster["hot"]), 6),
    }


def _profile(stories_by_id: dict[str, dict] | None = None) -> dict:
    now = time.time()
    interactions = storage.list_interactions(since_ts=now - PROFILE_LOOKBACK_DAYS * 86400)
    if stories_by_id is None:
        ids = list({i["story_id"] for i in interactions})
        stories_by_id = {s["id"]: s for s in storage.get_stories(ids)}
    else:
        missing = list({i["story_id"] for i in interactions} - stories_by_id.keys())
        stories_by_id = {**stories_by_id, **{s["id"]: s for s in storage.get_stories(missing)}}
    return ranking.build_profile(interactions, stories_by_id, storage.get_prefs())


def _hidden(actions: dict[str, set[str]]) -> set[str]:
    return {sid for sid, acted in actions.items() if "hide" in acted}


def _clusters(hours: float | None, now: float) -> tuple[list[dict], dict[str, dict]]:
    since = now - hours * 3600 if hours else now - RETENTION_DAYS * 86400
    stories = storage.list_stories(since_ts=since)
    # Popularity percentiles are always judged against the last three days,
    # so a long search window doesn't change what counts as "big".
    table = ranking.popularity_table([s for s in stories if s["published_at"] >= now - 72 * 3600] or stories)
    return ranking.build_clusters(stories, table, now), {s["id"]: s for s in stories}


def get_feed(
    view: str = "foryou",
    topic: str | None = None,
    source: str | None = None,
    q: str | None = None,
    limit: int = 30,
    offset: int = 0,
    hours: float | None = None,
) -> dict:
    now = time.time()
    if hours is None:
        hours = None if q else DEFAULT_HOURS  # searching looks through everything we have
    clusters, by_id = _clusters(hours, now)
    prefs = storage.get_prefs()
    actions = storage.story_actions()
    saved = storage.saved_ids()
    hidden = _hidden(actions)

    def keep(c: dict) -> bool:
        if c["lead"]["id"] in hidden or ranking.is_muted(c, prefs):
            return False
        if topic and topic not in c["topics"]:
            return False
        if source and source not in c["sources"]:
            return False
        if q and not ranking.matches_query(c, q):
            return False
        return True

    filtered = [c for c in clusters if keep(c)]
    profile = _profile(by_id) if view == "foryou" else None
    ranked = ranking.rank(filtered, view, profile)
    page = ranked[offset: offset + limit]
    return {
        "view": view,
        "total": len(ranked),
        "offset": offset,
        "has_more": offset + limit < len(ranked),
        "items": [_cluster_out(c, saved, actions) for c in page],
        "personalised": bool(profile and profile["signals"] > 0),
    }


def get_cluster(cluster_id: str) -> dict | None:
    now = time.time()
    clusters, _ = _clusters(None, now)
    for c in clusters:
        if c["id"] == cluster_id:
            return _cluster_out(c, storage.saved_ids(), storage.story_actions())
    return None


def get_catchup(limit: int = 30) -> dict:
    """Unseen clusters from the last day and a half, best first."""
    now = time.time()
    clusters, by_id = _clusters(CATCHUP_HOURS, now)
    prefs = storage.get_prefs()
    actions = storage.story_actions()
    saved = storage.saved_ids()

    def unseen(c: dict) -> bool:
        if ranking.is_muted(c, prefs):
            return False
        return not any(actions.get(s["id"], set()) & {"keep", "skip", "hide", "save"} for s in c["stories"])

    pending = [c for c in clusters if unseen(c)]
    ranked = ranking.rank(pending, "foryou", _profile(by_id))
    reviewed = len(clusters) - len(pending)
    return {
        "remaining": len(ranked),
        "reviewed": reviewed,
        "items": [_cluster_out(c, saved, actions) for c in ranked[:limit]],
    }


def get_profile() -> dict:
    profile = _profile()
    counts = profile["counts"]

    def table(kind: str, labels: dict, limit: int | None = None) -> list[dict]:
        rows = [
            {"id": k, "label": labels.get(k, k), "affinity": round(v, 3), "signals": counts[kind].get(k, 0)}
            for k, v in profile[kind].items()
        ]
        rows.sort(key=lambda r: r["affinity"], reverse=True)
        return rows[:limit] if limit else rows

    topic_labels = {t["id"]: t["label"] for t in TOPICS}
    source_labels = {s["id"]: s["short"] for s in SOURCES}
    terms = [r for r in table("terms", {}) if r["signals"] >= 2]
    stories = storage.get_stories(list({i["story_id"] for i in storage.list_interactions()}))
    term_labels = {k: v for s in stories for k, v in (s.get("terms") or {}).items()}
    for r in terms:
        r["label"] = term_labels.get(r["id"], r["id"])
    return {
        "signals": profile["signals"],
        "topics": table("topics", topic_labels),
        "sources": table("sources", source_labels),
        "liked_terms": [r for r in terms if r["affinity"] > 0][:12],
        "disliked_terms": sorted([r for r in terms if r["affinity"] < 0], key=lambda r: r["affinity"])[:8],
        "followed_topics": sorted(profile["followed"]),
    }


def get_trends(window: str = "24h") -> dict:
    now = time.time()
    cfg = WINDOWS[window]
    stories = storage.list_stories(since_ts=now - cfg["recent"] - cfg["baseline"])
    articles = [s for s in stories if s["source"] != "github"]
    terms = rising_terms(articles, now, window)
    by_id = {s["id"]: s for s in stories}
    saved, actions = storage.saved_ids(), storage.story_actions()
    for term in terms["terms"]:
        term["stories"] = [story_out(by_id[sid], saved, actions) for sid in term.pop("story_ids") if sid in by_id][:6]
    return {
        **terms,
        "topics": topic_volumes(stories, now, window),
        "generated_at": now,
    }


def quiz_id_for(round_no: int = 1, today: datetime | None = None) -> str:
    today = today or datetime.now()
    return f"{today:%Y-%m-%d}-r{round_no}"


def get_quiz(round_no: int = 1) -> dict:
    now = time.time()
    quiz_id = quiz_id_for(round_no)
    clusters, by_id = _clusters(7 * 24, now)
    stories = list(by_id.values())
    actions = storage.story_actions()
    seen = {sid for sid, acted in actions.items() if acted & {"open", "keep", "save"}}
    quiz = build_quiz(quiz_id, stories, clusters, seen)
    quiz["round"] = round_no
    return quiz


def get_status() -> dict:
    status = storage.get_source_status()
    run = ingest.last_run()
    sources = []
    for s in SOURCES:
        st = status.get(s["id"], {})
        sources.append(
            {
                "id": s["id"],
                "name": s["name"],
                "last_success": st.get("last_success"),
                "last_attempt": st.get("last_attempt"),
                "error": st.get("last_error"),
                "items": st.get("item_count"),
            }
        )
    successes = [s["last_success"] for s in sources if s["last_success"]]
    return {
        "fetching": ingest.is_running(),
        "last_run": run,
        "last_updated": max(successes) if successes else None,
        "story_count": storage.count_stories(),
        "interval_seconds": FETCH_INTERVAL_SECONDS,
        "sources": sources,
    }


def source_known(source_id: str) -> bool:
    return source_id in SOURCES_BY_ID
