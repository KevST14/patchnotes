"""Trend radar: which names are suddenly everywhere, and which topics are
getting louder.

A term is "rising" when it shows up in more stories in the recent window than
its usual rate — the baseline is the stretch just before the window, scaled
to the same length. Terms need at least a few stories from at least two
different sources, so one outlet's pet subject can't fake a trend.

Two details keep this honest:
- Single words only count if they look like names ("Nvidia", "Skydance",
  "AI") — otherwise "data" and "adds" win every day. Two-word phrases
  ("DGX Spark", "AI agents") are allowed through as they are.
- The baseline is worked out per source. RSS feeds only carry their latest
  few dozen items, so when Patch Notes is new, an outlet may have no history
  at all. Comparing its fresh stories against an empty past would make
  everything look like it's exploding, so a source only takes part in the
  comparison once its history covers enough of the baseline period.
"""

import math
from collections import Counter, defaultdict

from .clustering import find_entities
from .text import stem
from .topics import TOPICS

WINDOWS = {
    # recent: the window being judged; baseline: the comparison period just
    # before it; the sparkline shows `buckets` x `bucket` seconds ending now.
    "24h": {"recent": 86400, "baseline": 6 * 86400, "bucket": 12 * 3600, "buckets": 14},
    "7d": {"recent": 7 * 86400, "baseline": 21 * 86400, "bucket": 2 * 86400, "buckets": 14},
}

MIN_STORIES = 3
MIN_SOURCES = 2
MAX_RATIO = 8.0
MIN_RATIO = 1.25
# A single word is dropped when a phrase containing it accounts for this
# share of its stories — "DGX Spark" says more than "Spark" on its own.
BIGRAM_SUBSUME = 0.75

# Capitalised, so they look like names, but they never mean anything on a radar.
NOT_TRENDS = set(
    """
    january february march april may june july august september october november december
    monday tuesday wednesday thursday friday saturday sunday ceo cto cfo coo us usa uk q1 q2 q3 q4
    """.split()
)


def _spark(timestamps: list[float], now: float, bucket: int, buckets: int) -> list[int]:
    counts = [0] * buckets
    start = now - bucket * buckets
    for ts in timestamps:
        if ts < start or ts > now:
            continue
        counts[min(int((ts - start) // bucket), buckets - 1)] += 1
    return counts


def source_spans(stories: list[dict], now: float, cfg: dict) -> dict[str, float]:
    """For each source, how many seconds of the baseline period its stored
    history covers. Sources covering less than half a window are left out."""
    earliest: dict[str, float] = {}
    for s in stories:
        earliest[s["source"]] = min(earliest.get(s["source"], s["published_at"]), s["published_at"])
    recent_start = now - cfg["recent"]
    spans = {}
    for source, first in earliest.items():
        span = max(0.0, min(cfg["baseline"], recent_start - first))
        if span >= cfg["recent"] * 0.5:
            spans[source] = span
    return spans


class _Tally:
    """Recent count, and expected count from the baseline, for one key."""

    __slots__ = ("recent", "recent_comparable", "expected", "baseline_raw")

    def __init__(self):
        self.recent = 0
        self.recent_comparable = 0
        self.expected = 0.0
        self.baseline_raw = 0

    def ratio(self) -> float | None:
        if self.recent_comparable == 0 and self.expected == 0:
            return None
        return (self.recent_comparable + 1) / (self.expected + 1)


def _tally(stories, keys_of, now: float, cfg: dict, spans: dict[str, float]):
    recent_start = now - cfg["recent"]
    baseline_start = recent_start - cfg["baseline"]
    tallies: dict[str, _Tally] = defaultdict(_Tally)
    for s in stories:
        ts, source = s["published_at"], s["source"]
        for key in keys_of(s):
            t = tallies[key]
            if ts >= recent_start:
                t.recent += 1
                if source in spans:
                    t.recent_comparable += 1
            elif ts >= baseline_start and source in spans:
                t.baseline_raw += 1
                t.expected += cfg["recent"] / spans[source]
    return tallies


def rising_terms(stories: list[dict], now: float, window: str = "24h", limit: int = 24) -> dict:
    cfg = WINDOWS[window]
    recent_start = now - cfg["recent"]
    spark_start = now - cfg["bucket"] * cfg["buckets"]
    spans = source_spans(stories, now, cfg)
    entities = find_entities([s["title"] for s in stories])

    def keys_of(s):
        return [
            k for k in (s.get("terms") or {})
            if not any(w in NOT_TRENDS for w in k.split(" ")) and (" " in k or stem(k) in entities)
        ]

    tallies = _tally(stories, keys_of, now, cfg, spans)

    recent: dict[str, list[dict]] = defaultdict(list)
    labels: dict[str, Counter] = defaultdict(Counter)
    times: dict[str, list[float]] = defaultdict(list)
    for s in stories:
        ts = s["published_at"]
        for key in keys_of(s):
            if ts >= spark_start:
                times[key].append(ts)
            if ts >= recent_start:
                recent[key].append(s)
                labels[key][s["terms"][key]] += 1

    candidates = {}
    for key, items in recent.items():
        sources = {s["source"] for s in items}
        clusters = {s.get("cluster_id") or s["id"] for s in items}
        if len(items) < MIN_STORIES or len(sources) < MIN_SOURCES:
            continue
        # One story reposted on HN and Lobsters isn't a trend; one story that
        # three outlets wrote up, or a name in two separate stories, is.
        if len(sources) < 3 and len(clusters) < 2:
            continue
        tally = tallies[key]
        ratio = tally.ratio() if spans else None
        if ratio is not None and ratio < MIN_RATIO:
            continue  # it's busy, but that's normal for it
        spread = 1 + math.log2(len(sources))
        volume = math.log2(1 + len(items))
        score = volume * spread * (min(ratio, MAX_RATIO) if ratio is not None else 2.0)
        candidates[key] = {
            "key": key,
            "label": labels[key].most_common(1)[0][0],
            "count": len(items),
            "sources": sorted(sources),
            "clusters": len(clusters),
            "expected": round(tally.expected, 2),
            "ratio": round(ratio, 2) if ratio is not None else None,
            "is_new": ratio is None or tally.baseline_raw == 0,
            "score": round(score, 3),
            "spark": _spark(times[key], now, cfg["bucket"], cfg["buckets"]),
            "story_ids": [s["id"] for s in sorted(items, key=lambda s: s["published_at"], reverse=True)[:12]],
        }

    for key in [k for k in candidates if " " not in k]:
        for other, info in candidates.items():
            if " " in other and key in other.split(" ") and info["count"] >= BIGRAM_SUBSUME * candidates[key]["count"]:
                candidates.pop(key)
                break

    ranked = sorted(candidates.values(), key=lambda c: c["score"], reverse=True)[:limit]
    return {
        "window": window,
        "has_baseline": bool(spans),
        "baseline_sources": sorted(spans),
        "bucket_seconds": cfg["bucket"],
        "terms": ranked,
    }


def topic_volumes(stories: list[dict], now: float, window: str = "24h") -> list[dict]:
    cfg = WINDOWS[window]
    spans = source_spans(stories, now, cfg)
    tallies = _tally(stories, lambda s: s["topics"][:2], now, cfg, spans)

    times: dict[str, list[float]] = defaultdict(list)
    for s in stories:
        for topic in s["topics"][:2]:
            times[topic].append(s["published_at"])

    total_recent = sum(t.recent for t in tallies.values()) or 1
    out = []
    for topic in TOPICS:
        tid = topic["id"]
        tally = tallies.get(tid) or _Tally()
        change = (tally.recent_comparable - tally.expected) / tally.expected if tally.expected >= 1 else None
        out.append(
            {
                "id": tid,
                "label": topic["label"],
                "count": tally.recent,
                "share": round(tally.recent / total_recent, 3),
                "expected": round(tally.expected, 1) if spans else None,
                "change": round(change, 3) if change is not None else None,
                "spark": _spark(times[tid], now, cfg["bucket"], cfg["buckets"]),
            }
        )
    return sorted(out, key=lambda t: t["count"], reverse=True)
