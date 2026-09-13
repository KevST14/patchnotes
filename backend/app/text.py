"""Text helpers shared by ingest, clustering, trends and the quiz: HTML
cleanup, URL canonicalisation, and turning headlines into comparable tokens."""

import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)

# Boilerplate WordPress/Ghost feeds append to every summary.
_FEED_SUFFIXES = [
    re.compile(r"The post .+? appeared first on .+?\.?$", re.IGNORECASE),
    re.compile(r"Continue reading.*$", re.IGNORECASE),
    re.compile(r"Read (the )?(full|more).*$", re.IGNORECASE),
    re.compile(r"\[(&#8230;|…|\.\.\.)\]\s*$"),
]


def strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def clean_summary(raw: str | None, max_len: int = 320) -> str:
    text = strip_html(raw)
    for pattern in _FEED_SUFFIXES:
        text = pattern.sub("", text).strip()
    if len(text) > max_len:
        cut = text[:max_len].rsplit(" ", 1)[0]
        text = cut.rstrip(",.;:–—- ") + "…"
    return text


def html_to_paragraphs(raw: str | None) -> list[str]:
    """Comment bodies arrive as small HTML fragments; turn them into plain
    paragraphs so the frontend never has to render third-party HTML."""
    if not raw:
        return []
    parts = re.split(r"<p>|</p>|<br\s*/?>\s*<br\s*/?>|\n\n", raw)
    return [p for p in (strip_html(part) for part in parts) if p]


def first_image(raw: str | None) -> str | None:
    if not raw:
        return None
    match = _IMG_RE.search(raw)
    return html.unescape(match.group(1)) if match else None


# Affiliate/shopping posts that outlets mix into their main feeds. They're not
# news, and they'd swamp the feed (and the trends) if let through.
_JUNK_TITLE_RE = re.compile(
    r"\b(promo|coupon|discount) codes?\b"
    r"|\bcoupons?:"
    r"|^(today'?s|the best|best|early .*) .*\bdeals?\b"
    r"|^deals:"
    r"|^get (over )?\d+% off\b"
    r"|\bup to \$?\d+%? off\b.*\bmore$"
    r"|^\d+ best\b.*\(20\d\d\)"
    r"|^the \d+ best\b"
    r"|^save (up to )?\$?\d+"
    r"|\bdeals? of the day\b"
    r"|\b(prime day|black friday|cyber monday)\b.*\bdeals?\b",
    re.IGNORECASE,
)


def is_junk_title(title: str) -> bool:
    return bool(_JUNK_TITLE_RE.search(title.replace("’", "'")))


_TRACKING_PARAMS = {
    "ref", "ref_src", "ref_url", "fbclid", "gclid", "mc_cid", "mc_eid", "guccounter",
    "guce_referrer", "guce_referrer_sig", "soc_src", "soc_trk", "cmpid", "smid",
    "src", "source", "via", "share", "taid", "mbid", "rss",
}


def canonical_url(url: str) -> str:
    """Normalise a URL so the same article linked from two places compares
    equal: lowercase host without www., no fragment, no tracking params, no
    trailing slash."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    ]
    path = parts.path.rstrip("/") or ""
    return urlunsplit(("https", host, path, urlencode(sorted(query)), ""))


# --- tokenising ------------------------------------------------------------

STOPWORDS = set(
    """
    a about above after again against all almost also am an and any are aren't as at be because been
    before being below between both but by can can't cannot could couldn't did didn't do does doesn't
    doing don't down during each few for from further had hadn't has hasn't have haven't having he
    her here hers herself him himself his how i if in into is isn't it it's its itself just let's
    me more most much must my myself no nor not now of off on once only or other our ours ourselves
    out over own same she should shouldn't so some such than that that's the their theirs them
    themselves then there these they this those through to too under until up upon us very via
    was wasn't we were weren't what what's when where which while who whom whose why will with won't
    would wouldn't you you're your yours yourself yourselves vs versus per
    """.split()
)

# Words that show up in headlines constantly but say nothing about the story.
NEWS_FILLER = set(
    """
    new news says said say saying report reports reported reportedly announces announced announce
    launches launched launch launching unveils unveiled reveals revealed update updates updated get
    gets getting got make makes making made use uses using used first one two three now today week
    weeks year years day days month months time times best top latest big bigger biggest way ways
    thing things people want wants need needs know like look looks looking still even ever here's
    there's may might really actually finally officially soon already back
    deal deals sale sales off price prices review reviews hands-on hands vs show ask hn tell
    introducing introduces available coming comes come goes going go good bad better worse
    lot lots many every everything something anything nothing another how-to
    here our we've i'm i've you'll it'll who's
    gives give given take takes taking taken put puts set sets run runs running bring brings
    help helps keep keeps start starts started find finds found show shows shown free
    """.split()
)

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#'’.\-]*[A-Za-z0-9+#]|[A-Za-z0-9]")


def words(text: str) -> list[str]:
    """Split a headline into words, keeping things like 'GPT-5', 'C++',
    'Node.js' and 'M5' intact and dropping possessive 's."""
    out = []
    for raw in _WORD_RE.findall(text.replace("’", "'")):
        raw = raw.strip(".-'")
        if raw.endswith("'s"):
            raw = raw[:-2]
        if raw:
            out.append(raw)
    return out


def is_noise(word_lower: str) -> bool:
    return (
        word_lower in STOPWORDS
        or word_lower in NEWS_FILLER
        or len(word_lower) < 2
        or word_lower.replace(".", "").replace(",", "").isdigit() and len(word_lower) < 3
    )


def stem(word_lower: str) -> str:
    """A deliberately tiny stemmer: enough to match 'chips'/'chip' and
    'banned'/'bans' in clustering, without mangling product names."""
    w = word_lower
    if len(w) > 5 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith("ing"):
        return w[:-3]
    if len(w) > 4 and w.endswith("ed") and not w.endswith("eed"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is", "os")):
        return w[:-1]
    return w


def content_tokens(text: str) -> list[str]:
    """Stemmed, lowercased, non-noise tokens — the vocabulary clustering
    compares headlines on."""
    tokens = []
    for w in words(text):
        lw = w.lower()
        if is_noise(lw):
            continue
        tokens.append(stem(lw))
    return tokens


def extract_terms(title: str) -> dict[str, str]:
    """Candidate trend terms for a headline, as {key: display form}.

    Unigrams are any non-noise word that isn't a bare number; bigrams are two
    adjacent non-noise words (the second may be a number, so 'iPhone 17' and
    'Windows 11' survive). Keys are lowercase; the display form keeps the
    headline's own casing.
    """
    ws = words(title)
    terms: dict[str, str] = {}
    prev: str | None = None
    for w in ws:
        lw = w.lower()
        noise = is_noise(lw)
        numeric = lw.replace(".", "").isdigit()
        if not noise and not numeric:
            terms.setdefault(lw, w)
        if prev is not None and (not noise or numeric):
            if not (numeric and len(lw) > 4):  # skip years-ish / prices as bigram tails
                key = f"{prev.lower()} {lw}"
                terms.setdefault(key, f"{prev} {w}")
        prev = w if (not noise and not numeric) else None
    return terms
