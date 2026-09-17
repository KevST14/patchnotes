from app.clustering import cluster_stories, find_entities

from .helpers import NOW, make_story


def _clusters(stories):
    assignment = cluster_stories(stories)
    groups = {}
    for s in stories:
        groups.setdefault(assignment[s["id"]], set()).add(s["native_id"])
    return sorted(groups.values(), key=lambda g: sorted(g))


def test_same_article_from_two_aggregators_clusters_by_url():
    a = make_story(source="hn", native_id="1", title="A brief history", url="https://blog.example/post?utm_source=hn")
    b = make_story(source="lobsters", native_id="2", title="Something else entirely", url="https://blog.example/post/")
    assert _clusters([a, b]) == [{"1", "2"}]


def test_different_outlets_same_story_cluster_by_headline():
    a = make_story(source="bleeping", native_id="a", url="https://x/1", title="Fortinet warns of critical FortiMail flaw exploited in zero-day attacks")
    b = make_story(source="register", native_id="b", url="https://y/2", title="Fortinet sounds the alarm over actively exploited FortiMail zero-day")
    assert _clusters([a, b]) == [{"a", "b"}]


def test_shared_generic_words_do_not_cluster_different_stories():
    # Both are "critical flaw exploited" stories, but about different products.
    a = make_story(source="ars", native_id="a", url="https://x/1", title="Attackers have been exploiting critical Zimbra flaw to steal emails")
    b = make_story(source="bleeping", native_id="b", url="https://y/2", title="Fortinet warns of critical FortiMail flaw exploited in zero-day attacks")
    filler = [
        make_story(source="verge", native_id=f"f{i}", url=f"https://z/{i}", title=t)
        for i, t in enumerate(
            # Make "critical", "flaw" and "exploited" everyday words, as they
            # are in a real week of security news.
            [
                "Critical flaw found in old home routers",
                "Hackers exploited a critical bug in office printers",
                "Another critical flaw exploited in VPN appliances",
                "Critical patch fixes flaw in smart TVs",
            ]
        )
    ]
    clusters = _clusters([a, b, *filler])
    assert {"a"} in clusters and {"b"} in clusters


def test_same_source_series_does_not_cluster():
    a = make_story(source="9to5mac", native_id="a", url="https://x/1", title="9to5Mac Daily: October 2, 2026 – MacBook Pro rumors")
    b = make_story(source="9to5mac", native_id="b", url="https://x/2", title="9to5Mac Daily: October 1, 2026 – iPhone Duo production")
    assert _clusters([a, b]) == [{"a"}, {"b"}]


def test_stories_far_apart_in_time_do_not_cluster():
    a = make_story(source="ars", native_id="a", url="https://x/1", title="Micron says RAM shortage will continue", published_at=NOW - 10 * 86400)
    b = make_story(source="tomshw", native_id="b", url="https://y/2", title="Micron says RAM shortage will continue", published_at=NOW)
    assert _clusters([a, b]) == [{"a"}, {"b"}]


def test_cluster_id_is_earliest_story():
    a = make_story(source="ars", native_id="a", url="https://x/1", title="Paramount Warner Bros merger renamed Skydance", published_at=NOW - 7200)
    b = make_story(source="verge", native_id="b", url="https://y/2", title="Paramount’s Warner Bros. megamerger will be called Skydance", published_at=NOW - 3600)
    assignment = cluster_stories([b, a])
    assert assignment[a["id"]] == assignment[b["id"]] == a["id"]


def test_find_entities_uses_sentence_case_evidence():
    titles = [
        "The 7-year-old Nvidia Shield TV is now more expensive",
        "Gamers say the shield is too small",  # lowercase use of 'shield'
        "Why Nvidia keeps raising prices",
        "Cops Can Bypass Locked Phones",  # title case: tells us nothing
    ]
    entities = find_entities(titles)
    assert "nvidia" in entities
    assert "tv" in entities
    assert "shield" not in entities  # 1 upper vs 1 lower → not a name
    assert "cop" not in entities
