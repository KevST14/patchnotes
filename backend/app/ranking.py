"""Turning a pile of stories into a ranked feed.

Stories are grouped into clusters first (see clustering.py); everything below
ranks clusters, since "five outlets covered this" is itself a strong signal.

- *Latest*: newest first.
- *Top*: quality x freshness. Quality is each story's points/stars as a
  percentile *within its own source* (300 points on HN and 40 on Lobsters
  are both a big deal), a bonus for every extra outlet covering it, and a
  little for an active comment thread. Freshness halves roughly every 12
  hours. Outlet articles have no votes, so they get a fixed, below-median
  popularity — otherwise every brand-new post would outrank yesterday's
  biggest story. The ranked list is then lightly shuffled so one source
  can't fill the whole first screen.
- *For You*: Top, multiplied by how much you've liked stories like it. Every
  keep/save/open/skip/hide is a vote for or against that story's topics,
  source and headline terms; the profile is just those votes averaged with a
  little smoothing, so a single skip doesn't bury a whole topic.
"""

import math
import re
import time
from bisect import bisect_left
from collections import defaultdict

from .sources import SOURCES_BY_ID
from .topics import TOPICS_BY_ID

ACTION_WEIGHTS = {"keep": 1.0, "save": 2.0, "open": 0.6, "skip": -0.8, "hide": -2.0}
FOLLOW_BOOST = 0.8
# Outlet articles carry a summary and an image; aggregator posts (HN,
# Lobsters) carry the discussion. Prefer an outlet article as a cluster's face.
LEAD_PREFERENCE = {"rss": 0, "hn": 1, "lobsters": 2, "github": 3}
NO_SCORE_POPULARITY = 0.35
FRESHNESS_HALF_LIFE_HOURS = 12
# Each extra item from the same source already on the page multiplies a
# candidate's score by this, when diversifying.
SAME_SOURCE_DAMPING = 0.8


def popularity_table(stories: list[dict]) -> dict[str, list[int]]:
    """Sorted score lists per source, for percentile lookups."""
    table: dict[str, list[int]] = defaultdict(list)
    for s in stories:
        if s.get("score") is not None:
            table[s["source"]].append(s["score"])
    for scores in table.values():
        scores.sort()
    return table


def popularity(story: dict, table: dict[str, list[int]]) -> float:
    scores = table.get(story["source"])
    if story.get("score") is None or not scores:
        return NO_SCORE_POPULARITY
    # Scored sources only list stories that already did well (HN's front
    # page, GitHub repos past 40 stars), so their floor is 0.2, not 0.
    return 0.2 + 0.8 * bisect_left(scores, story["score"]) / max(len(scores) - 1, 1)


def _lead(members: list[dict]) -> dict:
    def key(s):
        kind = SOURCES_BY_ID.get(s["source"], {}).get("kind", "rss")
        return (LEAD_PREFERENCE.get(kind, 0), 0 if s.get("summary") else 1, 0 if s.get("image") else 1, s["published_at"])

    return min(members, key=key)


def build_clusters(stories: list[dict], table: dict[str, list[int]], now: float | None = None) -> list[dict]:
    now = now or time.time()
    groups: dict[str, list[dict]] = defaultdict(list)
    for s in stories:
        groups[s.get("cluster_id") or s["id"]].append(s)

    clusters = []
    for cluster_id, members in groups.items():
        members.sort(key=lambda s: s["published_at"])
        lead = _lead(members)
        sources = list(dict.fromkeys(s["source"] for s in members))
        topics = list(dict.fromkeys([*lead["topics"], *(t for s in members for t in s["topics"])]))
        first = members[0]["published_at"]
        last = members[-1]["published_at"]
        pop = max(popularity(s, table) for s in members)
        discussions = [
            {"story_id": s["id"], "source": s["source"], "url": s["discussion_url"], "score": s.get("score"), "comments": s.get("comments")}
            for s in members
            if s.get("discussion_url")
        ]
        comment_total = sum(d["comments"] or 0 for d in discussions)
        age_hours = max(0.0, (now - (first + last) / 2) / 3600)
        quality = 0.25 + pop + 0.6 * (len(sources) - 1) + math.log10(1 + comment_total) / 6
        hot = quality * 0.5 ** (age_hours / FRESHNESS_HALF_LIFE_HOURS)
        clusters.append(
            {
                "id": cluster_id,
                "lead": lead,
                "stories": members,
                "sources": sources,
                "source_count": len(sources),
                "topics": topics,
                "first_published": first,
                "last_published": last,
                "popularity": round(pop, 3),
                "discussions": discussions,
                "hot": hot,
            }
        )
    return clusters


# --- personalisation ------------------------------------------------------------

def build_profile(interactions: list[dict], stories_by_id: dict[str, dict], prefs: dict) -> dict:
    """Average the votes cast on each topic, source and headline term."""
    sums = {"topics": defaultdict(float), "sources": defaultdict(float), "terms": defaultdict(float)}
    counts = {"topics": defaultdict(int), "sources": defaultdict(int), "terms": defaultdict(int)}
    # Count each (story, action) once: opening the same story five times is
    # one signal, not five.
    seen = set()
    for it in interactions:
        story = stories_by_id.get(it["story_id"])
        weight = ACTION_WEIGHTS.get(it["action"])
        if story is None or weight is None or (it["story_id"], it["action"]) in seen:
            continue
        seen.add((it["story_id"], it["action"]))
        for topic in story["topics"][:2]:
            sums["topics"][topic] += weight
            counts["topics"][topic] += 1
        sums["sources"][story["source"]] += weight
        counts["sources"][story["source"]] += 1
        for term in story.get("terms") or {}:
            sums["terms"][term] += weight
            counts["terms"][term] += 1

    profile = {
        kind: {k: sums[kind][k] / (counts[kind][k] + 2) for k in sums[kind]}
        for kind in sums
    }
    profile["counts"] = {kind: dict(counts[kind]) for kind in counts}
    for topic in prefs.get("followed_topics", []):
        profile["topics"][topic] = profile["topics"].get(topic, 0.0) + FOLLOW_BOOST
    profile["followed"] = set(prefs.get("followed_topics", []))
    profile["signals"] = len(seen)
    return profile


def affinity(cluster: dict, profile: dict) -> tuple[float, list[str]]:
    """How much this cluster matches the profile, plus human-readable reasons."""
    lead = cluster["lead"]
    reasons = []
    topic_scores = [(t, profile["topics"].get(t, 0.0)) for t in cluster["topics"][:3]]
    topic_part = max((v for _, v in topic_scores), default=0.0)
    if topic_part < 0:
        topic_part = min(v for _, v in topic_scores)
    source_part = max((profile["sources"].get(s, 0.0) for s in cluster["sources"]), default=0.0)
    term_values = sorted((profile["terms"].get(t, 0.0) for t in lead.get("terms") or {}), key=abs, reverse=True)[:3]
    term_part = sum(term_values) / len(term_values) if term_values else 0.0

    score = 0.9 * topic_part + 0.35 * source_part + 0.5 * term_part
    best_topic = max(topic_scores, key=lambda x: x[1], default=None)
    if best_topic and best_topic[0] in profile["followed"]:
        reasons.append(f"You follow {TOPICS_BY_ID[best_topic[0]]['label']}")
    elif best_topic and best_topic[1] >= 0.25:
        reasons.append(f"You often keep {TOPICS_BY_ID[best_topic[0]]['label']} stories")
    if source_part >= 0.3:
        best_source = max(cluster["sources"], key=lambda s: profile["sources"].get(s, 0.0))
        reasons.append(f"You read a lot from {SOURCES_BY_ID[best_source]['short']}")
    if term_part >= 0.3:
        liked = max(lead.get("terms") or {}, key=lambda t: profile["terms"].get(t, 0.0))
        reasons.append(f"Mentions {lead['terms'][liked]}, which you've liked before")
    return max(-2.0, min(2.0, score)), reasons


def popularity_reasons(cluster: dict) -> list[str]:
    reasons = []
    if cluster["source_count"] >= 3:
        reasons.append(f"Covered by {cluster['source_count']} sources")
    for d in cluster["discussions"]:
        if d["source"] == "hn" and (d["score"] or 0) >= 300:
            reasons.append(f"Big on Hacker News ({d['score']} points)")
            break
    return reasons


def diversify(ranked: list[dict]) -> list[dict]:
    """Greedy re-rank: each pick dampens the remaining items from the same
    lead source, so the first screen is a mix rather than ten HN posts."""
    remaining = list(ranked)
    picked_per_source: dict[str, int] = defaultdict(int)
    out = []
    # Only the head of the list needs mixing; below that, plain order is fine.
    head = min(len(remaining), 60)
    while remaining and len(out) < head:
        best_i = max(
            range(min(len(remaining), 25)),
            key=lambda i: remaining[i]["score"] * SAME_SOURCE_DAMPING ** picked_per_source[remaining[i]["lead"]["source"]],
        )
        choice = remaining.pop(best_i)
        picked_per_source[choice["lead"]["source"]] += 1
        out.append(choice)
    return out + remaining


def rank(clusters: list[dict], view: str, profile: dict | None = None) -> list[dict]:
    if view == "latest":
        return sorted(clusters, key=lambda c: c["last_published"], reverse=True)
    for c in clusters:
        c["score"] = c["hot"]
        c["reasons"] = popularity_reasons(c)
        if view == "foryou" and profile is not None:
            aff, why = affinity(c, profile)
            c["affinity"] = round(aff, 3)
            c["score"] = c["hot"] * math.exp(aff)
            c["reasons"] = why + c["reasons"]
    return diversify(sorted(clusters, key=lambda c: c["score"], reverse=True))


def matches_query(cluster: dict, query: str) -> bool:
    words = [w for w in query.lower().split() if w]
    haystack = " ".join(f"{s['title']} {s.get('summary') or ''} {' '.join(s.get('source_tags') or [])}" for s in cluster["stories"]).lower()
    return all(w in haystack for w in words)


def is_muted(cluster: dict, prefs: dict) -> bool:
    muted_sources = set(prefs.get("muted_sources", []))
    if muted_sources and all(s in muted_sources for s in cluster["sources"]):
        return True
    titles = " ".join(s["title"] for s in cluster["stories"])
    return any(
        re.search(rf"(?<!\w){re.escape(term.strip())}(?!\w)", titles, re.IGNORECASE)
        for term in prefs.get("muted_terms", [])
        if term.strip()
    )
