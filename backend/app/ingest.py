"""One fetch cycle: pull every source, normalise, tag, store, re-cluster."""

import hashlib
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import fetchers, storage
from .clustering import cluster_stories
from .config import RETENTION_DAYS
from .sources import SOURCES
from .text import canonical_url, extract_terms, is_junk_title
from .topics import classify

log = logging.getLogger("ingest")

# Stories published within this window are re-clustered on every cycle, so
# late coverage of an older story still joins its cluster.
CLUSTER_WINDOW_SECONDS = 72 * 3600

# Some feeds carry 100 items; keeping the newest N stops one prolific outlet
# from drowning everything else.
MAX_ITEMS_PER_FEED = 40

_lock = threading.Lock()
_last_run: dict = {"started": None, "finished": None, "new": 0}


def story_id(source: str, native_id: str) -> str:
    return hashlib.sha1(f"{source}:{native_id}".encode()).hexdigest()[:16]


def enrich(raw: dict) -> dict:
    """Add the derived fields every stored story carries."""
    story = dict(raw)
    story["id"] = story_id(story["source"], story["native_id"])
    story["canonical_url"] = canonical_url(story["url"])
    story["topics"] = classify(story["title"], story.get("summary") or "", story.get("source_tags"))
    # Repo names aren't headlines; keep GitHub out of the trend vocabulary.
    story["terms"] = extract_terms(story["title"]) if story["source"] != "github" else {}
    return story


def _fetch_source(client, source: dict, status: dict, backfill: bool) -> list[dict] | None:
    kind = source["kind"]
    try:
        if kind == "hn":
            raw = fetchers.fetch_hn(client, backfill=backfill)
        elif kind == "lobsters":
            raw = fetchers.fetch_lobsters(client)
        elif kind == "github":
            raw = fetchers.fetch_github(client)
        else:
            prev = status.get(source["id"]) or {}
            raw, etag, last_modified = fetchers.fetch_rss(
                client, source, etag=prev.get("etag"), last_modified=prev.get("last_modified")
            )
            raw = sorted(raw, key=lambda s: s["published_at"], reverse=True)[:MAX_ITEMS_PER_FEED]
            storage.record_source_attempt(
                source["id"], ok=True, item_count=len(raw), etag=etag, last_modified=last_modified
            )
            return raw
        storage.record_source_attempt(source["id"], ok=True, item_count=len(raw))
        return raw
    except fetchers.NotModified:
        storage.record_source_attempt(source["id"], ok=True)
        return []
    except Exception as exc:  # one broken source must never sink the whole cycle
        log.warning("fetch failed for %s: %s", source["id"], exc)
        storage.record_source_attempt(source["id"], ok=False, error=str(exc)[:300])
        return None


def recluster(now: float | None = None) -> int:
    now = now or time.time()
    recent = storage.list_stories(since_ts=now - CLUSTER_WINDOW_SECONDS)
    assignment = cluster_stories(recent)
    storage.set_cluster_ids(assignment)
    return len(set(assignment.values()))


def run_cycle(sources: list[dict] | None = None) -> dict:
    """Fetch everything once. Safe to call from the scheduler and from the
    manual refresh endpoint at the same time — the second caller just waits."""
    with _lock:
        started = time.time()
        _last_run["started"] = started
        backfill = storage.count_stories() == 0
        status = storage.get_source_status()
        sources = sources or SOURCES

        with fetchers._client() as client, ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda s: _fetch_source(client, s, status, backfill), sources))

        stories: dict[str, dict] = {}
        for raw_list in results:
            for raw in raw_list or []:
                if is_junk_title(raw["title"]):
                    continue
                story = enrich(raw)
                stories[story["id"]] = story

        new = storage.upsert_stories(list(stories.values()))
        clusters = recluster()
        pruned = storage.prune_stories(time.time() - RETENTION_DAYS * 86400)

        _last_run.update({"finished": time.time(), "new": new})
        log.info(
            "cycle done in %.1fs: %d fetched, %d new, %d clusters in window, %d pruned",
            time.time() - started, len(stories), new, clusters, pruned,
        )
        return {"fetched": len(stories), "new": new, "clusters": clusters, "pruned": pruned}


def is_running() -> bool:
    return _lock.locked()


def last_run() -> dict:
    return dict(_last_run)
