"""Headline quiz, generated from the week's stories — no LLM needed.

Question types:
- blank:    a headline with one name or number taken out; pick what goes there.
            Wrong answers are names of the same kind (companies for a company,
            people for a person) that were *also* in this week's news, so you
            can't just pick the one that sounds familiar.
- outlet:   which outlet ran this headline?
- hn:       which of these got the most points on Hacker News?
- coverage: which of these did the most outlets cover?

A quiz is seeded from its id (the date plus a round number), so reloading the
page gives you the same questions, and "new round" gives you fresh ones.
Stories you opened or kept are three times as likely to be picked — it's a
quiz on what stuck, not on what you never saw.
"""

import hashlib
import random
import re

from .sources import SOURCES_BY_ID

KNOWN_ENTITIES = {
    "company": """
        Apple Google Alphabet Microsoft Meta Amazon OpenAI Anthropic Nvidia NVIDIA AMD Intel Samsung
        Tesla SpaceX Netflix Spotify TikTok ByteDance Huawei Xiaomi Sony Nintendo Valve IBM Oracle
        Cloudflare GitHub Qualcomm TSMC Arm Broadcom Cisco Dell HP Lenovo Reddit Uber Waymo Rivian
        Fortinet Micron Adobe Salesforce Figma Discord Mozilla Telegram Coinbase Binance xAI
        DeepSeek Mistral Perplexity Synopsys Palantir Flock Paramount Disney Verizon T-Mobile
        Comcast Seagate Hynix Asus Acer MSI Razer Logitech Garmin Fitbit Peloton Stripe Shopify
        Airbnb DoorDash Lyft Snap Pinterest Yahoo Dropbox Zoom Slack Atlassian GitLab Vercel
        Supabase HashiCorp Canonical Proton Kagi DuckDuckGo Ubisoft Activision Blizzard Bungie
        Roblox Unity Boeing Airbus Alibaba Tencent Baidu Kaspersky CrowdStrike SoftBank Foxconn ASML
        Siemens Bosch Ford Toyota Volkswagen BYD Polestar Lucid Zoox Anduril Cohere Midjourney
        ElevenLabs Replit Cursor Netlify Fastly Akamai Twilio Okta Wiz Zscaler SentinelOne Mandiant
        Snowflake Databricks Micron JetBrains Framework Nothing OnePlus Motorola Nokia Ericsson
        """,
    "product": """
        iPhone iPad MacBook iMac Pixel Galaxy Windows Android ChatGPT Claude Gemini Copilot Chrome
        Firefox Safari Linux Steam PS5 PlayStation Xbox Kindle Starlink Starship AirPods Siri
        Alexa Llama Grok Sora Gmail Outlook Excel YouTube Instagram WhatsApp Threads Bluesky
        Mastodon Twitter Facebook Messenger Photoshop Notion Arduino Ubuntu Fedora Debian macOS iOS
        iPadOS watchOS visionOS Rust Python JavaScript TypeScript Kubernetes Docker Postgres SQLite
        Git Zig Kotlin Java Ryzen Radeon GeForce RTX Xeon EPYC Snapdragon Exynos HomePod Chromebook
        Thunderbird Signal Cybertruck Dots Muse Codex Gmail Wikipedia Reddit Netflix Spotify
        """,
    "person": """
        Musk Altman Zuckerberg Nadella Pichai Bezos Jassy Huang Amodei Trump Biden Vance Gates
        Wozniak Torvalds Ternus Federighi Hassabis Sutskever Karpathy LeCun Hinton Murati Brockman
        Gelsinger Thiel Andreessen Dorsey Spiegel Chesky Ellison Benioff Newsom Lutnick Bessent
        """,
}


def _entity_kinds() -> dict[str, str]:
    kinds = {}
    for kind, blob in KNOWN_ENTITIES.items():
        # Multi-word names are written with spaces in the blob, so match
        # single tokens only; that's enough for blanking one word.
        for name in blob.split():
            kinds.setdefault(name.lower(), kind)
    return kinds


ENTITY_KINDS = _entity_kinds()

_NUMBER_RE = re.compile(
    r"(?P<pre>\$)?(?P<num>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?P<post>%|\s?(?:million|billion|trillion)\b|[MBK]\b|x\b)?",
    re.IGNORECASE,
)
_WORD_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+&.\-]*[A-Za-z0-9+]|[A-Za-z]")

BLANK = "_____"


def _seed(quiz_id: str) -> int:
    return int(hashlib.sha1(quiz_id.encode()).hexdigest()[:12], 16)


def _story_ref(story: dict) -> dict:
    return {
        "id": story["id"],
        "title": story["title"],
        "url": story["url"],
        "source": story["source"],
        "published_at": story["published_at"],
    }


def _format_number(value: float, template: str) -> str:
    if "," in template:
        return f"{int(round(value)):,}"
    if "." in template:
        decimals = len(template.split(".")[1])
        return f"{value:.{decimals}f}"
    return str(int(round(value)))


def number_distractors(match: re.Match, rng: random.Random) -> list[str] | None:
    raw = match.group("num")
    value = float(raw.replace(",", ""))
    if value < 2 or (not match.group("pre") and not match.group("post")):
        return None  # bare small numbers ("3 reasons") make dull questions
    pre, post = match.group("pre") or "", match.group("post") or ""
    if post == "%":
        pool = [value * f for f in (0.5, 0.65, 1.5, 2.0, 0.3)]
        pool = [p for p in pool if 0 < p <= 100]
    else:
        pool = [value * f for f in (0.25, 0.5, 2.0, 3.0, 1.5, 10.0)]
    seen = {_format_number(value, raw)}
    out = []
    rng.shuffle(pool)
    for p in pool:
        text = _format_number(p, raw)
        if text not in seen:
            seen.add(text)
            out.append(f"{pre}{text}{post}")
        if len(out) == 3:
            return out
    return None


def _entity_pool(stories: list[dict]) -> dict[str, list[str]]:
    """Every curated name seen in this week's headlines, by kind, written
    the way the headlines write it."""
    pool: dict[str, dict[str, str]] = {kind: {} for kind in KNOWN_ENTITIES}
    for s in stories:
        for w in _WORD_TOKEN_RE.findall(s["title"].replace("’", "'")):
            kind = ENTITY_KINDS.get(w.lower())
            if kind and any(c.isupper() for c in w):
                pool[kind].setdefault(w.lower(), w)
    return {k: list(v.values()) for k, v in pool.items()}


def make_blank(story: dict, pool: dict[str, list[str]], rng: random.Random) -> dict | None:
    title = story["title"]
    tokens = _WORD_TOKEN_RE.findall(title.replace("’", "'"))
    if len(tokens) < 6:
        return None  # "_____ 1.0" isn't a question, it's a guess
    candidates = []
    for w in tokens:
        kind = ENTITY_KINDS.get(w.lower())
        if kind and any(c.isupper() for c in w):
            candidates.append((0, w, kind))
    for m in _NUMBER_RE.finditer(title):
        candidates.append((1, m, "number"))
    rng.shuffle(candidates)
    candidates.sort(key=lambda c: c[0])

    for _, answer, kind in candidates:
        if kind == "number":
            distractors = number_distractors(answer, rng)
            if not distractors:
                continue
            answer_text = answer.group(0).strip()
            prompt = title[: answer.start()] + BLANK + title[answer.end():]
        else:
            answer_text = answer
            others = [e for e in pool.get(kind, []) if e.lower() != answer.lower() and e.lower() not in title.lower()]
            if len(others) < 3:
                # Not enough same-kind names in this week's news: fall back to
                # the curated list so it's still a fair fight.
                extra = [n for n, k in _CANONICAL.items() if k == kind and n.lower() not in title.lower() and n.lower() != answer.lower()]
                rng.shuffle(extra)
                others += [e for e in extra if e not in others]
            if len(others) < 3:
                continue
            distractors = rng.sample(others[:30], 3)
            prompt = re.sub(rf"(?<![\w-]){re.escape(answer)}(?![\w-])", BLANK, title.replace("’", "'"))
            if BLANK not in prompt:
                continue
        options = [answer_text, *distractors]
        rng.shuffle(options)
        return {
            "type": "blank",
            "prompt": "Fill in the blank",
            "headline": prompt,
            "options": options,
            "answer": options.index(answer_text),
            "explanation": f"{SOURCES_BY_ID[story['source']]['short']}: “{title}”",
            "story": _story_ref(story),
        }
    return None


# Display casing for the curated names, for fallback distractors.
_CANONICAL = {}
for _kind, _blob in KNOWN_ENTITIES.items():
    for _name in _blob.split():
        _CANONICAL.setdefault(_name, _kind)


def make_outlet(story: dict, outlets: list[str], rng: random.Random) -> dict | None:
    others = [o for o in outlets if o != story["source"]]
    if len(others) < 3:
        return None
    options_ids = [story["source"], *rng.sample(others, 3)]
    rng.shuffle(options_ids)
    return {
        "type": "outlet",
        "prompt": "Which outlet ran this headline?",
        "headline": story["title"],
        "options": [SOURCES_BY_ID[o]["name"] for o in options_ids],
        "answer": options_ids.index(story["source"]),
        "explanation": f"It was {SOURCES_BY_ID[story['source']]['name']}.",
        "story": _story_ref(story),
    }


def make_hn(hn_stories: list[dict], rng: random.Random) -> dict | None:
    pool = [s for s in hn_stories if s.get("score")]
    for _ in range(20):
        if len(pool) < 4:
            return None
        picks = rng.sample(pool, 4)
        scores = sorted((s["score"] for s in picks), reverse=True)
        if scores[0] >= 1.25 * scores[1]:
            break
    else:
        return None
    winner = max(picks, key=lambda s: s["score"])
    return {
        "type": "hn",
        "prompt": "Which got the most points on Hacker News?",
        "headline": None,
        "options": [s["title"] for s in picks],
        "option_values": [f"{s['score']:,} points" for s in picks],
        "answer": picks.index(winner),
        "explanation": f"“{winner['title']}” reached {winner['score']:,} points.",
        "story": _story_ref(winner),
    }


def make_coverage(clusters: list[dict], rng: random.Random, exclude: set[str] = frozenset()) -> dict | None:
    multi = [c for c in clusters if c["source_count"] >= 2 and c["id"] not in exclude]
    singles = [c for c in clusters if c["source_count"] == 1]
    if not multi or len(multi) + len(singles) < 4:
        return None
    multi.sort(key=lambda c: c["source_count"], reverse=True)
    for _ in range(20):
        top = rng.choice(multi[:6])
        rest_pool = [c for c in multi + singles if c["source_count"] < top["source_count"]]
        if len(rest_pool) < 3:
            continue
        picks = [top, *rng.sample(rest_pool, 3)]
        rng.shuffle(picks)
        return {
            "type": "coverage",
            "prompt": "Which story did the most outlets cover?",
            "headline": None,
            "options": [c["lead"]["title"] for c in picks],
            "option_values": [f"{c['source_count']} source{'s' if c['source_count'] != 1 else ''}" for c in picks],
            "answer": picks.index(top),
            "explanation": "Covered by " + ", ".join(SOURCES_BY_ID[s]["short"] for s in top["sources"]) + ".",
            "story": _story_ref(top["lead"]),
        }
    return None


def build_quiz(quiz_id: str, stories: list[dict], clusters: list[dict], seen_ids: set[str], length: int = 8) -> dict:
    rng = random.Random(_seed(quiz_id))
    articles = sorted((s for s in stories if s["source"] != "github"), key=lambda s: s["id"])
    pool = _entity_pool(articles)

    # Weighted shuffle (Efraimidis–Spirakis): bigger stories and ones you
    # engaged with come up more often, but anything can appear.
    importance = {}
    for c in clusters:
        for s in c["stories"]:
            importance[s["id"]] = 1 + 1.5 * (c["source_count"] - 1) + 2 * c["popularity"]

    def weight(s: dict) -> float:
        return importance.get(s["id"], 1.0) * (3.0 if s["id"] in seen_ids else 1.0)

    weighted = sorted(articles, key=lambda s: rng.random() ** (1 / weight(s)), reverse=True)

    questions: list[dict] = []
    # Track clusters, not stories: three questions about the same Micron
    # earnings story from three outlets would be one question asked thrice.
    cluster_of = {s["id"]: s.get("cluster_id") or s["id"] for s in stories}
    used: set[str] = set()

    def take(q: dict | None):
        cluster = cluster_of.get(q["story"]["id"], q["story"]["id"]) if q else None
        if q and cluster not in used and len(questions) < length:
            used.add(cluster)
            q["seen"] = q["story"]["id"] in seen_ids
            questions.append(q)
            return True
        return False

    plan = ["blank", "outlet", "blank", "hn", "blank", "coverage", "outlet", "blank"]
    outlets = sorted({s["source"] for s in articles if SOURCES_BY_ID[s["source"]]["kind"] == "rss"})
    hn = [s for s in articles if s["source"] == "hn"]
    candidates = iter(weighted)

    for kind in plan:
        if kind == "hn":
            if take(make_hn(hn, rng)):
                continue
        elif kind == "coverage":
            if take(make_coverage(clusters, rng, exclude=used)):
                continue
        # blank / outlet, and the fallback when hn/coverage can't be built
        for story in candidates:
            if cluster_of[story["id"]] in used:
                continue
            if kind == "outlet" and SOURCES_BY_ID[story["source"]]["kind"] == "rss":
                q = make_outlet(story, outlets, rng)
            else:
                q = make_blank(story, pool, rng)
            if take(q):
                break

    for i, q in enumerate(questions):
        q["id"] = f"{quiz_id}-{i}"
    return {"id": quiz_id, "questions": questions, "pool_size": len(articles)}
