"""Top comments from the Hacker News / Lobsters thread behind a story, so you
can see what people are saying without leaving the feed. Comment bodies are
flattened to plain-text paragraphs here; the frontend never renders
third-party HTML."""

import time

from .fetchers import HN_SEARCH, LOBSTERS, SourceError, _client, _get_json
from .text import html_to_paragraphs

CACHE_SECONDS = 300
_cache: dict[str, tuple[float, dict]] = {}


def _count(node: dict) -> int:
    return sum(1 + _count(c) for c in node.get("children") or [])


def parse_hn_thread(item: dict, limit: int = 6) -> list[dict]:
    comments = []
    # Algolia returns top-level comments in HN's own ranking order.
    for child in item.get("children") or []:
        if child.get("type") != "comment" or not child.get("text") or not child.get("author"):
            continue
        comments.append(
            {
                "author": child["author"],
                "paragraphs": html_to_paragraphs(child["text"])[:6],
                "created_at": child.get("created_at_i"),
                "replies": _count(child),
                "url": f"https://news.ycombinator.com/item?id={child['id']}",
            }
        )
        if len(comments) == limit:
            break
    return comments


def parse_lobsters_thread(story: dict, limit: int = 6) -> list[dict]:
    comments = story.get("comments") or []
    replies: dict[str, int] = {}
    for c in comments:
        parent = c.get("parent_comment")
        if parent:
            replies[parent] = replies.get(parent, 0) + 1
    top = [c for c in comments if c.get("depth") == 0 and not c.get("is_deleted")]
    top.sort(key=lambda c: c.get("score") or 0, reverse=True)
    out = []
    for c in top[:limit]:
        user = c.get("commenting_user")
        out.append(
            {
                "author": user if isinstance(user, str) else (user or {}).get("username", "?"),
                "paragraphs": html_to_paragraphs(c.get("comment"))[:6],
                "score": c.get("score"),
                "replies": replies.get(c.get("short_id"), 0),
                "url": c.get("url") or c.get("short_id_url"),
            }
        )
    return out


def fetch_discussion(story: dict) -> dict:
    """Comments for one HN or Lobsters story. Cached briefly, since people
    tend to open and close the same thread a few times."""
    key = story["id"]
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    with _client() as client:
        if story["source"] == "hn":
            item = _get_json(client, f"{HN_SEARCH}/items/{story['native_id']}")
            comments = parse_hn_thread(item)
        elif story["source"] == "lobsters":
            data = _get_json(client, f"{LOBSTERS}/s/{story['native_id']}.json")
            comments = parse_lobsters_thread(data)
        else:
            raise SourceError(f"{story['source']} has no discussion thread")
    result = {
        "story_id": story["id"],
        "source": story["source"],
        "url": story["discussion_url"],
        "total": story.get("comments"),
        "comments": comments,
    }
    _cache[key] = (time.time(), result)
    return result

