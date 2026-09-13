"""Fetch each source and normalise what comes back into one story shape.

Every parser is a pure function from a raw payload to a list of story dicts,
kept separate from the HTTP call so the tests can feed them fixtures.

Story shape:
    source, native_id, title, url, discussion_url, summary, image, author,
    published_at (unix seconds), score, comments, source_tags
"""

import calendar
import logging
import time
from datetime import datetime, timezone

import feedparser
import httpx

from .config import BACKFILL_DAYS, GITHUB_TOKEN, USER_AGENT
from .text import clean_summary, first_image, strip_html

log = logging.getLogger("fetchers")

HN_SEARCH = "https://hn.algolia.com/api/v1"
LOBSTERS = "https://lobste.rs"
GITHUB_API = "https://api.github.com"

TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class SourceError(Exception):
    pass


class NotModified(Exception):
    """The feed answered 304 to a conditional GET: nothing new since last time."""


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def _get_json(client: httpx.Client, url: str, **kwargs):
    try:
        resp = client.get(url, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SourceError(f"{url}: {exc}") from exc


def _iso_to_ts(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# --- Hacker News (via Algolia's search API) --------------------------------

def parse_hn_hits(hits: list[dict]) -> list[dict]:
    stories = []
    for hit in hits:
        title = (hit.get("title") or "").strip()
        object_id = hit.get("objectID") or hit.get("story_id")
        if not title or not object_id:
            continue
        discussion = f"https://news.ycombinator.com/item?id={object_id}"
        stories.append(
            {
                "source": "hn",
                "native_id": str(object_id),
                "title": title,
                "url": hit.get("url") or discussion,
                "discussion_url": discussion,
                "summary": clean_summary(hit.get("story_text")),
                "image": None,
                "author": hit.get("author"),
                "published_at": float(hit.get("created_at_i") or time.time()),
                "score": hit.get("points"),
                "comments": hit.get("num_comments"),
                "source_tags": [],
            }
        )
    return stories


def fetch_hn(client: httpx.Client, backfill: bool = False) -> list[dict]:
    front = _get_json(client, f"{HN_SEARCH}/search", params={"tags": "front_page", "hitsPerPage": 60})
    hits = list(front.get("hits", []))
    # Front page is a snapshot of right now; also catch anything that did
    # well recently but already scrolled off. On first run, go back further.
    days = BACKFILL_DAYS if backfill else 2
    since = int(time.time() - days * 86400)
    for page in range(4 if backfill else 1):
        recent = _get_json(
            client,
            f"{HN_SEARCH}/search_by_date",
            params={
                "tags": "story",
                "numericFilters": f"created_at_i>{since},points>120",
                "hitsPerPage": 100,
                "page": page,
            },
        )
        hits.extend(recent.get("hits", []))
        if page + 1 >= recent.get("nbPages", 0):
            break
    return parse_hn_hits(hits)


# --- Lobsters ----------------------------------------------------------------

def parse_lobsters(items: list[dict]) -> list[dict]:
    stories = []
    for item in items:
        title = (item.get("title") or "").strip()
        if not title or not item.get("short_id"):
            continue
        stories.append(
            {
                "source": "lobsters",
                "native_id": item["short_id"],
                "title": title,
                "url": item.get("url") or item.get("comments_url") or item["short_id_url"],
                "discussion_url": item.get("comments_url") or item.get("short_id_url"),
                "summary": clean_summary(item.get("description")),
                "image": None,
                "author": item.get("submitter_user") if isinstance(item.get("submitter_user"), str)
                else (item.get("submitter_user") or {}).get("username"),
                "published_at": _iso_to_ts(item.get("created_at")) or time.time(),
                "score": item.get("score"),
                "comments": item.get("comment_count"),
                "source_tags": list(item.get("tags") or []),
            }
        )
    return stories


def fetch_lobsters(client: httpx.Client, backfill: bool = False) -> list[dict]:
    items = list(_get_json(client, f"{LOBSTERS}/hottest.json"))
    items += list(_get_json(client, f"{LOBSTERS}/page/2.json"))
    return parse_lobsters(items)


# --- GitHub: repos created recently that are collecting stars fast ----------

def parse_github(items: list[dict]) -> list[dict]:
    stories = []
    for repo in items:
        if not repo.get("full_name"):
            continue
        description = (repo.get("description") or "").strip()
        tags = [t for t in (repo.get("topics") or [])]
        if repo.get("language"):
            tags.insert(0, repo["language"].lower())
        stories.append(
            {
                "source": "github",
                "native_id": str(repo.get("id") or repo["full_name"]),
                "title": repo["full_name"] + (f": {description}" if description else ""),
                "url": repo["html_url"],
                "discussion_url": None,
                "summary": clean_summary(description),
                "image": None,
                "author": (repo.get("owner") or {}).get("login"),
                "published_at": _iso_to_ts(repo.get("created_at")) or time.time(),
                "score": repo.get("stargazers_count"),
                "comments": None,
                "source_tags": tags,
                "extra": {
                    "repo": repo["full_name"],
                    "language": repo.get("language"),
                    "forks": repo.get("forks_count"),
                },
            }
        )
    return stories


def fetch_github(client: httpx.Client, backfill: bool = False) -> list[dict]:
    since = datetime.fromtimestamp(time.time() - 7 * 86400, tz=timezone.utc).strftime("%Y-%m-%d")
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    data = _get_json(
        client,
        f"{GITHUB_API}/search/repositories",
        params={"q": f"created:>{since} stars:>40", "sort": "stars", "order": "desc", "per_page": 30},
        headers=headers,
    )
    return parse_github(data.get("items", []))


# --- RSS / Atom ----------------------------------------------------------------

def _entry_image(entry) -> str | None:
    for key in ("media_thumbnail", "media_content"):
        for media in entry.get(key) or []:
            url = media.get("url")
            if url and (media.get("medium") in (None, "image") or "image" in (media.get("type") or "image")):
                return url
    for link in entry.get("links") or []:
        if link.get("rel") == "enclosure" and (link.get("type") or "").startswith("image"):
            return link.get("href")
    for content in entry.get("content") or []:
        img = first_image(content.get("value"))
        if img:
            return img
    return first_image(entry.get("summary"))


def _entry_time(entry) -> float | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            return float(calendar.timegm(parsed))
    return None


def parse_feed(source_id: str, body: bytes | str) -> list[dict]:
    feed = feedparser.parse(body)
    if feed.bozo and not feed.entries:
        raise SourceError(f"{source_id}: unparseable feed ({feed.bozo_exception})")
    now = time.time()
    stories = []
    for entry in feed.entries:
        title = strip_html(entry.get("title"))
        link = entry.get("link")
        if not title or not link:
            continue
        summary_html = entry.get("summary") or ""
        if not summary_html and entry.get("content"):
            summary_html = entry["content"][0].get("value", "")
        published = _entry_time(entry) or now
        stories.append(
            {
                "source": source_id,
                "native_id": entry.get("id") or link,
                "title": title,
                "url": link,
                "discussion_url": None,
                "summary": clean_summary(summary_html),
                "image": _entry_image(entry),
                "author": strip_html(entry.get("author")) or None,
                # Some feeds post-date by a few minutes; never let a story be "from the future".
                "published_at": min(published, now),
                "score": None,
                "comments": None,
                "source_tags": [strip_html(t.get("term")) for t in entry.get("tags") or [] if t.get("term")],
            }
        )
    return stories


def fetch_rss(client: httpx.Client, source: dict, etag: str | None = None, last_modified: str | None = None):
    """Returns (stories, etag, last_modified). Raises NotModified on a 304."""
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    try:
        resp = client.get(source["url"], headers=headers)
    except httpx.HTTPError as exc:
        raise SourceError(f"{source['id']}: {exc}") from exc
    if resp.status_code == 304:
        raise NotModified()
    if resp.status_code >= 400:
        raise SourceError(f"{source['id']}: HTTP {resp.status_code}")
    stories = parse_feed(source["id"], resp.content)
    return stories, resp.headers.get("etag"), resp.headers.get("last-modified")
