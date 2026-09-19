from app import ranking

from .helpers import NOW, make_story


def _cluster(story, **overrides):
    story = {**story, "cluster_id": story["id"]}
    [c] = ranking.build_clusters([story], ranking.popularity_table([story]), NOW)
    c.update(overrides)
    return c


def test_popularity_is_a_percentile_within_each_source():
    hn = [make_story(source="hn", native_id=str(i), url=f"https://x/{i}", score=s) for i, s in enumerate([100, 400, 1600])]
    lob = [make_story(source="lobsters", native_id=f"l{i}", url=f"https://y/{i}", score=s) for i, s in enumerate([5, 40])]
    table = ranking.popularity_table(hn + lob)
    assert ranking.popularity(hn[2], table) == 1.0
    assert ranking.popularity(lob[1], table) == 1.0  # 40 is a lot on Lobsters
    assert ranking.popularity(hn[0], table) == 0.2
    assert ranking.popularity(make_story(), table) == ranking.NO_SCORE_POPULARITY


def test_cluster_lead_prefers_outlet_article_over_aggregator_post():
    hn = make_story(source="hn", native_id="1", url="https://ars/x", title="Shield TV price hike", published_at=NOW - 7200, score=300, discussion_url="https://hn/1")
    ars = make_story(source="ars", native_id="2", url="https://ars/x", title="Shield TV price hike", summary="It costs more.", published_at=NOW - 3600)
    for s in (hn, ars):
        s["cluster_id"] = hn["id"]
    [c] = ranking.build_clusters([hn, ars], ranking.popularity_table([hn, ars]), NOW)
    assert c["lead"]["id"] == ars["id"]
    assert c["source_count"] == 2
    assert c["discussions"][0]["source"] == "hn"


def test_coverage_beats_freshness_in_top():
    covered = [
        make_story(source=src, native_id=src, url=f"https://{src}/x", title="Story", published_at=NOW - 6 * 3600)
        for src in ("ars", "verge", "register")
    ]
    for s in covered:
        s["cluster_id"] = covered[0]["id"]
    fresh = make_story(source="wired", native_id="w", url="https://wired/x", title="Other", published_at=NOW - 600)
    fresh["cluster_id"] = fresh["id"]
    stories = covered + [fresh]
    clusters = ranking.build_clusters(stories, ranking.popularity_table(stories), NOW)
    top = ranking.rank(clusters, "top")
    assert top[0]["source_count"] == 3


def test_profile_learns_from_keeps_and_skips():
    ai = make_story(native_id="ai", url="https://x/ai", title="OpenAI ships a new chatbot")
    games = make_story(native_id="g", url="https://x/g", title="Nintendo Switch 2 game sales")
    interactions = [
        {"story_id": ai["id"], "action": "keep"},
        {"story_id": ai["id"], "action": "save"},
        {"story_id": games["id"], "action": "skip"},
    ]
    profile = ranking.build_profile(interactions, {ai["id"]: ai, games["id"]: games}, {"followed_topics": []})
    assert profile["topics"]["ai"] > 0 > profile["topics"]["gaming"]

    new_ai = _cluster(make_story(native_id="ai2", url="https://x/ai2", title="Anthropic releases a chatbot update"))
    new_games = _cluster(make_story(native_id="g2", url="https://x/g2", title="Xbox game pass price rises"))
    assert ranking.affinity(new_ai, profile)[0] > 0 > ranking.affinity(new_games, profile)[0]


def test_repeated_opens_count_once():
    s = make_story(native_id="x", url="https://x/x", title="OpenAI ships a new chatbot")
    once = ranking.build_profile([{"story_id": s["id"], "action": "open"}], {s["id"]: s}, {})
    many = ranking.build_profile([{"story_id": s["id"], "action": "open"}] * 5, {s["id"]: s}, {})
    assert once["topics"] == many["topics"]


def test_followed_topic_boosts_and_explains():
    profile = ranking.build_profile([], {}, {"followed_topics": ["security"]})
    c = _cluster(make_story(native_id="s", url="https://x/s", title="Ransomware gang arrested"))
    score, reasons = ranking.affinity(c, profile)
    assert score > 0
    assert reasons == ["You follow Security"]


def test_diversify_breaks_up_runs_from_one_source():
    clusters = [
        {"score": 1.0 - i * 0.01, "lead": {"source": "hn" if i < 6 else "ars"}} for i in range(8)
    ]
    out = ranking.diversify(clusters)
    first_five = [c["lead"]["source"] for c in out[:5]]
    assert "ars" in first_five


def test_muted_terms_match_whole_words_only():
    c = _cluster(make_story(native_id="m", url="https://x/m", title="Officials said the rollout is delayed"))
    assert not ranking.is_muted(c, {"muted_terms": ["AI"]})
    assert ranking.is_muted(c, {"muted_terms": ["rollout"]})


def test_query_requires_every_word():
    c = _cluster(make_story(native_id="q", url="https://x/q", title="Nvidia debuts DGX Spark", summary="A tiny AI box"))
    assert ranking.matches_query(c, "dgx box")
    assert not ranking.matches_query(c, "dgx phone")
