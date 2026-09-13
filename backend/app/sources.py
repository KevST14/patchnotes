"""Every place Patch Notes pulls stories from. All of them are free and keyless.

`kind` picks the fetcher: "hn" and "lobsters" are community link aggregators
with votes and comments, "github" is newly created repos gaining stars fast,
and "rss" is an outlet's own feed (RSS or Atom; feedparser handles both).
"""

SOURCES = [
    {
        "id": "hn",
        "name": "Hacker News",
        "short": "HN",
        "kind": "hn",
        "homepage": "https://news.ycombinator.com",
        "color": "#ff6600",
    },
    {
        "id": "lobsters",
        "name": "Lobsters",
        "short": "Lobsters",
        "kind": "lobsters",
        "homepage": "https://lobste.rs",
        "color": "#ac130d",
    },
    {
        "id": "github",
        "name": "GitHub (rising repos)",
        "short": "GitHub",
        "kind": "github",
        "homepage": "https://github.com",
        "color": "#8250df",
    },
    {
        "id": "ars",
        "name": "Ars Technica",
        "short": "Ars",
        "kind": "rss",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "homepage": "https://arstechnica.com",
        "color": "#ff4e00",
    },
    {
        "id": "verge",
        "name": "The Verge",
        "short": "Verge",
        "kind": "rss",
        "url": "https://www.theverge.com/rss/index.xml",
        "homepage": "https://www.theverge.com",
        "color": "#5200ff",
    },
    {
        "id": "techcrunch",
        "name": "TechCrunch",
        "short": "TechCrunch",
        "kind": "rss",
        "url": "https://techcrunch.com/feed/",
        "homepage": "https://techcrunch.com",
        "color": "#0a9e01",
    },
    {
        "id": "wired",
        "name": "Wired",
        "short": "Wired",
        "kind": "rss",
        "url": "https://www.wired.com/feed/rss",
        "homepage": "https://www.wired.com",
        "color": "#7a7a7a",
    },
    {
        "id": "engadget",
        "name": "Engadget",
        "short": "Engadget",
        "kind": "rss",
        "url": "https://www.engadget.com/rss.xml",
        "homepage": "https://www.engadget.com",
        "color": "#1e90ff",
    },
    {
        "id": "404media",
        "name": "404 Media",
        "short": "404 Media",
        "kind": "rss",
        "url": "https://www.404media.co/rss/",
        "homepage": "https://www.404media.co",
        "color": "#e0218a",
    },
    {
        "id": "techreview",
        "name": "MIT Technology Review",
        "short": "MIT TR",
        "kind": "rss",
        "url": "https://www.technologyreview.com/feed/",
        "homepage": "https://www.technologyreview.com",
        "color": "#c41230",
    },
    {
        "id": "bleeping",
        "name": "BleepingComputer",
        "short": "Bleeping",
        "kind": "rss",
        "url": "https://www.bleepingcomputer.com/feed/",
        "homepage": "https://www.bleepingcomputer.com",
        "color": "#2a6db0",
    },
    {
        "id": "9to5mac",
        "name": "9to5Mac",
        "short": "9to5Mac",
        "kind": "rss",
        "url": "https://9to5mac.com/feed/",
        "homepage": "https://9to5mac.com",
        "color": "#3fa9f5",
    },
    {
        "id": "register",
        "name": "The Register",
        "short": "Register",
        "kind": "rss",
        "url": "https://www.theregister.com/headlines.atom",
        "homepage": "https://www.theregister.com",
        "color": "#cc0000",
    },
    {
        "id": "tomshw",
        "name": "Tom's Hardware",
        "short": "Tom's HW",
        "kind": "rss",
        "url": "https://www.tomshardware.com/feeds.xml",
        "homepage": "https://www.tomshardware.com",
        "color": "#e4002b",
    },
]

SOURCES_BY_ID = {s["id"]: s for s in SOURCES}


def public_sources() -> list[dict]:
    """The registry minus fetch-only details, for the frontend."""
    return [
        {k: s[k] for k in ("id", "name", "short", "kind", "homepage", "color")}
        for s in SOURCES
    ]
