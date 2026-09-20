from app.trends import rising_terms, source_spans, topic_volumes, WINDOWS

from .helpers import NOW, make_story

HOUR = 3600
DAY = 86400


def _background(days: int = 6):
    """Steady daily chatter from three sources across the baseline period,
    so every source has enough history to be compared."""
    stories = []
    for d in range(1, days + 1):
        for src in ("ars", "verge", "register"):
            stories.append(
                make_story(
                    source=src,
                    native_id=f"{src}-{d}",
                    url=f"https://{src}/{d}",
                    title=f"Apple updates Safari on day {d}" if d % 2 else f"Google tweaks Chrome tabs again {d}",
                    published_at=NOW - d * DAY - 2 * HOUR,
                )
            )
    return stories


def test_new_name_across_sources_is_rising():
    stories = _background() + [
        make_story(source=src, native_id=f"sky-{src}", url=f"https://{src}/sky", title=title, published_at=NOW - h * HOUR)
        for src, title, h in [
            ("ars", "Paramount merger will be called Skydance", 2),
            ("verge", "Skydance is the new name for Warner Bros", 3),
            ("register", "Why Skydance, though?", 5),
        ]
    ]
    result = rising_terms(stories, NOW, "24h")
    labels = [t["label"] for t in result["terms"]]
    assert "Skydance" in labels
    sky = next(t for t in result["terms"] if t["label"] == "Skydance")
    assert sky["is_new"] and sky["count"] == 3 and len(sky["sources"]) == 3
    assert result["has_baseline"]


def test_steady_names_are_not_rising():
    stories = _background() + [
        make_story(source=src, native_id=f"apple-{src}", url=f"https://{src}/apple-now", title="Apple updates Safari again", published_at=NOW - 2 * HOUR)
        for src in ("ars",)
    ]
    labels = [t["label"] for t in rising_terms(stories, NOW, "24h")["terms"]]
    assert "Apple" not in labels


def test_single_source_cannot_make_a_trend():
    stories = _background() + [
        make_story(source="ars", native_id=f"z{i}", url=f"https://ars/z{i}", title=f"Zircon kernel news number {i}", published_at=NOW - i * HOUR)
        for i in range(1, 6)
    ]
    labels = [t["label"] for t in rising_terms(stories, NOW, "24h")["terms"]]
    assert "Zircon" not in labels


def test_generic_words_are_not_trends():
    stories = _background() + [
        make_story(source=src, native_id=f"d-{src}-{i}", url=f"https://{src}/d{i}", title=f"Companies want more data about you {i}", published_at=NOW - (i + 1) * HOUR)
        for src in ("ars", "verge")
        for i in range(3)
    ]
    labels = [t["label"].lower() for t in rising_terms(stories, NOW, "24h")["terms"]]
    assert "data" not in labels


def test_sources_without_history_sit_out_the_baseline():
    # wired only has stories from the last few hours, so it can't be judged
    # against a past it doesn't have.
    stories = _background() + [make_story(source="wired", native_id="w", url="https://wired/w", title="x", published_at=NOW - HOUR)]
    spans = source_spans(stories, NOW, WINDOWS["24h"])
    assert "wired" not in spans
    assert spans["ars"] > 0


def test_topic_volumes_report_change_against_baseline():
    stories = _background()
    stories += [
        make_story(source=src, native_id=f"sec-{src}-{i}", url=f"https://{src}/s{i}", title=f"Ransomware gang hits hospital {i}", published_at=NOW - (i + 1) * HOUR)
        for src in ("ars", "verge")
        for i in range(3)
    ]
    volumes = {t["id"]: t for t in topic_volumes(stories, NOW, "24h")}
    assert volumes["security"]["count"] == 6
    assert len(volumes["security"]["spark"]) == WINDOWS["24h"]["buckets"]
    assert sum(volumes["security"]["spark"]) == 6
