"""Group stories from different sources that are about the same thing.

Two passes:
1. Stories that link the exact same article (after URL canonicalisation) are
   always one cluster — e.g. an Ars piece that's also on the HN front page.
2. Headlines are compared as TF-IDF vectors, so rare words like 'Shield'
   count far more than common ones like 'Apple'. Names count double on top
   of that: "critical flaw exploited" is shared by every security story of
   the week, so whether two headlines are both about *Fortinet* is what
   decides it. Stories are visited oldest first, and each joins the cluster
   whose *centroid* it's most similar to, if that clears the threshold —
   otherwise it starts a new one. Comparing against centroids rather than
   single members stops the chaining you get with single-link clustering,
   where A~B and B~C drags in an unrelated C.
"""

import math
import re
from collections import Counter, defaultdict

from .text import is_noise, stem, words

SIMILARITY_THRESHOLD = 0.34
ENTITY_WEIGHT = 2.0
MAX_GAP_SECONDS = 48 * 3600

_YEAR_RE = re.compile(r"^(19|20)\d\d$")


def _headline_tokens(title: str) -> list[tuple[str, str, bool]]:
    """(stemmed key, original word, is_first_word) for each content word."""
    out = []
    for i, w in enumerate(words(title)):
        lw = w.lower()
        if is_noise(lw) or _YEAR_RE.match(lw):
            continue
        out.append((stem(lw), w, i == 0))
    return out


def _is_title_case(title: str) -> bool:
    """'Cops Can Bypass iPhone's Automatic Reboot' capitalises every word, so
    its casing says nothing about which words are names."""
    ws = [w for w in words(title) if w[0].isalpha() and w.lower() not in ("a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "at", "by", "with")]
    if len(ws) < 3:
        return True
    return sum(1 for w in ws if w[0].isupper()) / len(ws) > 0.7


def find_entities(titles: list[str]) -> set[str]:
    """Stemmed tokens that look like names: written with a capital in the
    middle of sentence-case headlines more often than not, or shaped like a
    product name (mixed case like 'iPhone', or containing a digit like 'M5')."""
    upper, lower = Counter(), Counter()
    entities = set()
    for title in titles:
        title_case = _is_title_case(title)
        for key, original, first in _headline_tokens(title):
            if any(c.isdigit() for c in original) and any(c.isalpha() for c in original):
                entities.add(key)
            elif original[1:] != original[1:].lower() and not original.isupper():
                entities.add(key)  # iPhone, OpenAI, FortiMail
            if first or title_case:
                continue
            if original[0].isupper():
                upper[key] += 1
            else:
                lower[key] += 1
    entities.update(k for k in upper if upper[k] > lower[k])
    return entities


def _vectorise(token_lists: list[list[str]], entities: set[str]) -> list[dict[str, float]]:
    n = len(token_lists)
    df = Counter()
    for tokens in token_lists:
        df.update(set(tokens))
    vectors = []
    for tokens in token_lists:
        tf = Counter(tokens)
        vec = {
            # Smoothed IDF (+1) so a word shared by every story in a tiny
            # window still counts for something instead of exactly zero.
            t: (1 + math.log(c)) * (math.log((1 + n) / (1 + df[t])) + 1) * (ENTITY_WEIGHT if t in entities else 1.0)
            for t, c in tf.items()
        }
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vectors.append({t: v / norm for t, v in vec.items()})
    return vectors


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(t, 0.0) for t, v in a.items())


class _Cluster:
    __slots__ = ("index", "members", "centroid_sum", "latest", "tokens", "sources", "_centroid")

    def __init__(self, index: int):
        self.index = index
        self.members: list[int] = []
        self.centroid_sum: dict[str, float] = defaultdict(float)
        self.latest = 0.0
        self.tokens: set[str] = set()
        self.sources: set[str] = set()
        self._centroid: dict[str, float] | None = None

    def add(self, idx: int, vec: dict[str, float], ts: float, source: str):
        self.members.append(idx)
        self.sources.add(source)
        for t, v in vec.items():
            self.centroid_sum[t] += v
        self.tokens.update(vec)
        self.latest = max(self.latest, ts)
        self._centroid = None

    def centroid(self) -> dict[str, float]:
        if self._centroid is None:
            norm = math.sqrt(sum(v * v for v in self.centroid_sum.values())) or 1.0
            self._centroid = {t: v / norm for t, v in self.centroid_sum.items()}
        return self._centroid


def cluster_stories(stories: list[dict], threshold: float = SIMILARITY_THRESHOLD) -> dict[str, str]:
    """Map story id -> cluster id. A cluster's id is the id of its earliest
    story, so it stays stable as later coverage joins it.

    Each story needs: id, title, canonical_url, published_at, source.
    GitHub repos never cluster with articles by headline (their 'headline' is
    a repo name and description) but still group by identical URL.
    """
    order = sorted(range(len(stories)), key=lambda i: (stories[i]["published_at"], stories[i]["id"]))
    titled = [s["title"] if s["source"] != "github" else "" for s in stories]
    entities = find_entities(titled)
    tokens = [[key for key, _, _ in _headline_tokens(t)] for t in titled]
    vectors = _vectorise(tokens, entities)

    clusters: list[_Cluster] = []
    by_url: dict[str, _Cluster] = {}
    # Inverted index token -> clusters containing it, so each story only
    # compares against clusters it shares at least one word with.
    by_token: dict[str, set[int]] = defaultdict(set)

    for idx in order:
        story = stories[idx]
        vec = vectors[idx]
        ts = story["published_at"]
        target = by_url.get(story["canonical_url"])

        if target is None and vec:
            candidates = set()
            for t in vec:
                candidates |= by_token.get(t, set())
            best, best_sim = None, threshold
            for ci in candidates:
                cluster = clusters[ci]
                if ts - cluster.latest > MAX_GAP_SECONDS:
                    continue
                # An outlet's recurring series ("9to5Mac Daily: ...", "The
                # Download: ...") looks alike every day; a cluster is about
                # *different* outlets covering one story.
                if story["source"] in cluster.sources:
                    continue
                # Require two shared words: one shared rare word ("Pi")
                # is too easy to hit by coincidence on short titles.
                if len(cluster.tokens & vec.keys()) < 2:
                    continue
                sim = _cosine(vec, cluster.centroid())
                if sim >= best_sim:
                    best, best_sim = cluster, sim
            target = best

        if target is None:
            target = _Cluster(len(clusters))
            clusters.append(target)
        target.add(idx, vec, ts, story["source"])
        by_url.setdefault(story["canonical_url"], target)
        for t in vec:
            by_token[t].add(target.index)

    assignment = {}
    for cluster in clusters:
        root = stories[cluster.members[0]]["id"]
        for idx in cluster.members:
            assignment[stories[idx]["id"]] = root
    return assignment
