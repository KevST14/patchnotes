import json
import sqlite3
import time
from contextlib import contextmanager

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS stories (
    id TEXT PRIMARY KEY,          -- sha1(source:native_id), first 16 hex chars
    source TEXT NOT NULL,
    native_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    discussion_url TEXT,
    summary TEXT,
    image TEXT,
    author TEXT,
    published_at REAL NOT NULL,
    first_seen REAL NOT NULL,
    score INTEGER,
    comments INTEGER,
    source_tags TEXT,             -- JSON list, as the source labelled it
    topics TEXT,                  -- JSON list of topic ids, strongest first
    terms TEXT,                   -- JSON {key: display} trend-term candidates
    extra TEXT,                   -- JSON, source-specific bits (e.g. repo language)
    cluster_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_stories_published ON stories (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_stories_cluster ON stories (cluster_id);
CREATE INDEX IF NOT EXISTS idx_stories_canonical ON stories (canonical_url);

-- Every keep/skip/open/save/hide, so the For You ranking can learn from it.
CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id TEXT NOT NULL,
    action TEXT NOT NULL,
    ts REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_interactions_story ON interactions (story_id);
CREATE INDEX IF NOT EXISTS idx_interactions_ts ON interactions (ts DESC);

CREATE TABLE IF NOT EXISTS saved (
    story_id TEXT PRIMARY KEY,
    saved_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS prefs (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL           -- JSON
);

CREATE TABLE IF NOT EXISTS source_status (
    source TEXT PRIMARY KEY,
    last_attempt REAL,
    last_success REAL,
    last_error TEXT,
    item_count INTEGER,
    etag TEXT,
    last_modified TEXT
);

CREATE TABLE IF NOT EXISTS quiz_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id TEXT NOT NULL,
    score INTEGER NOT NULL,
    total INTEGER NOT NULL,
    taken_at REAL NOT NULL
);
"""

ACTIONS = ("keep", "skip", "open", "save", "hide")

DEFAULT_PREFS = {"followed_topics": [], "muted_terms": [], "muted_sources": []}


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        # WAL lets the API keep reading while the fetcher thread writes.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)


def _row_to_story(row: sqlite3.Row) -> dict:
    story = dict(row)
    for key, default in (("source_tags", []), ("topics", []), ("terms", {}), ("extra", {})):
        story[key] = json.loads(story[key]) if story.get(key) else default
    return story


# --- stories -----------------------------------------------------------------

def upsert_stories(stories: list[dict]) -> int:
    """Insert new stories; for ones already stored, refresh the fields that
    change over time (score, comments, title edits, summary). Returns how
    many were new."""
    now = time.time()
    with get_db() as conn:
        existing = {
            r["id"]
            for r in conn.execute(
                f"SELECT id FROM stories WHERE id IN ({','.join('?' * len(stories))})",
                [s["id"] for s in stories],
            )
        } if stories else set()
        for s in stories:
            conn.execute(
                """
                INSERT INTO stories (id, source, native_id, title, url, canonical_url, discussion_url,
                    summary, image, author, published_at, first_seen, score, comments, source_tags,
                    topics, terms, extra, cluster_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title, summary=excluded.summary,
                    image=COALESCE(excluded.image, stories.image),
                    score=excluded.score, comments=excluded.comments,
                    source_tags=excluded.source_tags, topics=excluded.topics,
                    terms=excluded.terms, extra=excluded.extra
                """,
                (
                    s["id"], s["source"], s["native_id"], s["title"], s["url"], s["canonical_url"],
                    s.get("discussion_url"), s.get("summary"), s.get("image"), s.get("author"),
                    s["published_at"], now, s.get("score"), s.get("comments"),
                    json.dumps(s.get("source_tags") or []), json.dumps(s.get("topics") or []),
                    json.dumps(s.get("terms") or {}), json.dumps(s.get("extra") or {}),
                    s["id"],
                ),
            )
    return len([s for s in stories if s["id"] not in existing])


def list_stories(since_ts: float | None = None, until_ts: float | None = None) -> list[dict]:
    clauses, params = [], []
    if since_ts is not None:
        clauses.append("published_at >= ?")
        params.append(since_ts)
    if until_ts is not None:
        clauses.append("published_at < ?")
        params.append(until_ts)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_db() as conn:
        rows = conn.execute(f"SELECT * FROM stories {where} ORDER BY published_at DESC", params).fetchall()
        return [_row_to_story(r) for r in rows]


def get_story(story_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
        return _row_to_story(row) if row else None


def get_stories(story_ids: list[str]) -> list[dict]:
    if not story_ids:
        return []
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM stories WHERE id IN ({','.join('?' * len(story_ids))})", story_ids
        ).fetchall()
        return [_row_to_story(r) for r in rows]


def set_cluster_ids(assignment: dict[str, str]) -> None:
    with get_db() as conn:
        conn.executemany(
            "UPDATE stories SET cluster_id = ? WHERE id = ?",
            [(cluster_id, story_id) for story_id, cluster_id in assignment.items()],
        )


def count_stories() -> int:
    with get_db() as conn:
        return conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]


def prune_stories(older_than_ts: float) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM stories WHERE published_at < ? AND id NOT IN (SELECT story_id FROM saved)",
            (older_than_ts,),
        )
        return cur.rowcount


# --- interactions --------------------------------------------------------------

def record_interaction(story_id: str, action: str, ts: float | None = None) -> None:
    if action not in ACTIONS:
        raise ValueError(f"unknown action '{action}'")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO interactions (story_id, action, ts) VALUES (?, ?, ?)",
            (story_id, action, ts or time.time()),
        )


def undo_last_interaction(story_id: str, actions: tuple[str, ...] = ("keep", "skip", "save")) -> str | None:
    """Remove the most recent triage decision on a story (catch-up's undo)."""
    with get_db() as conn:
        row = conn.execute(
            f"SELECT id, action FROM interactions WHERE story_id = ? AND action IN ({','.join('?' * len(actions))})"
            " ORDER BY ts DESC, id DESC LIMIT 1",
            (story_id, *actions),
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM interactions WHERE id = ?", (row["id"],))
        if row["action"] == "save":
            conn.execute("DELETE FROM saved WHERE story_id = ?", (story_id,))
        return row["action"]


def list_interactions(since_ts: float | None = None) -> list[dict]:
    with get_db() as conn:
        if since_ts is None:
            rows = conn.execute("SELECT * FROM interactions ORDER BY ts DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM interactions WHERE ts >= ? ORDER BY ts DESC", (since_ts,)
            ).fetchall()
        return [dict(r) for r in rows]


def story_actions() -> dict[str, set[str]]:
    """story id -> every action ever taken on it."""
    out: dict[str, set[str]] = {}
    with get_db() as conn:
        for r in conn.execute("SELECT DISTINCT story_id, action FROM interactions"):
            out.setdefault(r["story_id"], set()).add(r["action"])
    return out


# --- saved ---------------------------------------------------------------------

def save_story(story_id: str) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO saved (story_id, saved_at) VALUES (?, ?) ON CONFLICT(story_id) DO NOTHING",
            (story_id, time.time()),
        )


def unsave_story(story_id: str) -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM saved WHERE story_id = ?", (story_id,))


def saved_ids() -> dict[str, float]:
    with get_db() as conn:
        return {r["story_id"]: r["saved_at"] for r in conn.execute("SELECT * FROM saved")}


# --- prefs ---------------------------------------------------------------------

def get_prefs() -> dict:
    prefs = dict(DEFAULT_PREFS)
    with get_db() as conn:
        for r in conn.execute("SELECT key, value FROM prefs"):
            prefs[r["key"]] = json.loads(r["value"])
    return prefs


def set_prefs(updates: dict) -> dict:
    with get_db() as conn:
        for key, value in updates.items():
            if key not in DEFAULT_PREFS:
                raise ValueError(f"unknown pref '{key}'")
            conn.execute(
                "INSERT INTO prefs (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )
    return get_prefs()


# --- source status -------------------------------------------------------------

def get_source_status() -> dict[str, dict]:
    with get_db() as conn:
        return {r["source"]: dict(r) for r in conn.execute("SELECT * FROM source_status")}


def record_source_attempt(
    source: str,
    *,
    ok: bool,
    error: str | None = None,
    item_count: int | None = None,
    etag: str | None = None,
    last_modified: str | None = None,
) -> None:
    now = time.time()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO source_status (source, last_attempt, last_success, last_error, item_count, etag, last_modified)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                last_attempt=excluded.last_attempt,
                last_success=COALESCE(excluded.last_success, source_status.last_success),
                last_error=excluded.last_error,
                item_count=COALESCE(excluded.item_count, source_status.item_count),
                etag=COALESCE(excluded.etag, source_status.etag),
                last_modified=COALESCE(excluded.last_modified, source_status.last_modified)
            """,
            (source, now, now if ok else None, None if ok else error, item_count, etag, last_modified),
        )


# --- quiz ----------------------------------------------------------------------

def record_quiz_result(quiz_id: str, score: int, total: int) -> dict:
    now = time.time()
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO quiz_results (quiz_id, score, total, taken_at) VALUES (?, ?, ?, ?)",
            (quiz_id, score, total, now),
        )
        return {"id": cur.lastrowid, "quiz_id": quiz_id, "score": score, "total": total, "taken_at": now}


def list_quiz_results(limit: int = 20) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM quiz_results ORDER BY taken_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
