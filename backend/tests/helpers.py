import time

NOW = time.time()


def make_story(**overrides) -> dict:
    """A fully-enriched story dict, as ingest.enrich would produce."""
    from app.ingest import enrich

    raw = {
        "source": "ars",
        "native_id": overrides.get("url", "https://example.com/a"),
        "title": "Nvidia debuts DGX Spark with half the RAM",
        "url": "https://example.com/a",
        "discussion_url": None,
        "summary": "",
        "image": None,
        "author": None,
        "published_at": NOW - 3600,
        "score": None,
        "comments": None,
        "source_tags": [],
    }
    raw.update(overrides)
    return enrich(raw)
