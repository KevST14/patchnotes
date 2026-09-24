import pytest
from fastapi.testclient import TestClient

from app import ingest
from app.main import app

from .helpers import NOW, make_story


@pytest.fixture
def client(storage):
    # Not used as a context manager, so the lifespan (and its scheduler,
    # which would fetch from the real internet) never starts.
    stories = [
        make_story(source="ars", native_id="a1", url="https://ars/1", title="Fortinet warns of critical FortiMail flaw exploited in zero-day attacks", published_at=NOW - 3600),
        make_story(source="register", native_id="r1", url="https://reg/1", title="Fortinet sounds the alarm over actively exploited FortiMail zero-day", published_at=NOW - 1800),
        make_story(source="hn", native_id="h1", url="https://blog/1", title="Show HN: A tiny Rust compiler", score=400, comments=120, discussion_url="https://news.ycombinator.com/item?id=h1", published_at=NOW - 7200),
        make_story(source="verge", native_id="v1", url="https://verge/1", title="Nintendo Switch 2 sales top expectations", published_at=NOW - 600),
    ]
    storage.upsert_stories(stories)
    ingest.recluster(NOW)
    return TestClient(app), {s["native_id"]: s["id"] for s in stories}


def test_meta_lists_sources_and_topics(client):
    c, _ = client
    meta = c.get("/api/meta").json()
    assert any(s["id"] == "hn" for s in meta["sources"])
    assert any(t["id"] == "ai" for t in meta["topics"])


def test_feed_groups_coverage_into_one_item(client):
    c, ids = client
    feed = c.get("/api/feed", params={"view": "top"}).json()
    assert feed["total"] == 3
    fortinet = next(i for i in feed["items"] if "Fortinet" in i["lead"]["title"])
    assert fortinet["source_count"] == 2
    assert len(fortinet["coverage"]) == 1


def test_feed_filters(client):
    c, _ = client
    assert c.get("/api/feed", params={"topic": "gaming"}).json()["total"] == 1
    assert c.get("/api/feed", params={"source": "hn"}).json()["total"] == 1
    assert c.get("/api/feed", params={"q": "fortimail zero-day"}).json()["total"] == 1
    assert c.get("/api/feed", params={"view": "sideways"}).status_code == 400
    assert c.get("/api/feed", params={"topic": "knitting"}).status_code == 400


def test_hide_removes_from_feed_and_save_shows_in_saved(client):
    c, ids = client
    assert c.post("/api/interactions", json={"story_id": ids["v1"], "action": "hide"}).status_code == 200
    titles = [i["lead"]["title"] for i in c.get("/api/feed").json()["items"]]
    assert not any("Nintendo" in t for t in titles)

    assert c.put(f"/api/saved/{ids['h1']}").status_code == 200
    saved = c.get("/api/saved").json()
    assert [s["id"] for s in saved] == [ids["h1"]]
    assert saved[0]["saved"] is True
    c.delete(f"/api/saved/{ids['h1']}")
    assert c.get("/api/saved").json() == []


def test_interaction_validation(client):
    c, ids = client
    assert c.post("/api/interactions", json={"story_id": "nope", "action": "keep"}).status_code == 404
    assert c.post("/api/interactions", json={"story_id": ids["v1"], "action": "love"}).status_code == 400


def test_catchup_shrinks_as_you_triage_and_undo_restores(client):
    c, ids = client
    before = c.get("/api/catchup").json()
    assert before["remaining"] == 3
    first = before["items"][0]["lead"]["id"]
    c.post("/api/interactions", json={"story_id": first, "action": "skip"})
    assert c.get("/api/catchup").json()["remaining"] == 2
    assert c.post(f"/api/interactions/{first}/undo").json()["undone"] == "skip"
    assert c.get("/api/catchup").json()["remaining"] == 3


def test_keeping_shapes_the_profile(client):
    c, ids = client
    c.post("/api/interactions", json={"story_id": ids["a1"], "action": "keep"})
    profile = c.get("/api/profile").json()
    assert profile["signals"] == 1
    assert profile["topics"][0]["id"] == "security"
    assert profile["topics"][0]["affinity"] > 0


def test_prefs_validation(client):
    c, _ = client
    assert c.put("/api/prefs", json={"followed_topics": ["ai"]}).json()["followed_topics"] == ["ai"]
    assert c.put("/api/prefs", json={"followed_topics": ["knitting"]}).status_code == 400
    prefs = c.put("/api/prefs", json={"muted_terms": [" crypto ", "", "Crypto", "NFT"]}).json()
    assert prefs["muted_terms"] == ["crypto", "Crypto", "NFT"] or prefs["muted_terms"] == ["Crypto", "crypto", "NFT"]


def test_muted_term_hides_story(client):
    c, _ = client
    c.put("/api/prefs", json={"muted_terms": ["nintendo"]})
    titles = [i["lead"]["title"] for i in c.get("/api/feed").json()["items"]]
    assert not any("Nintendo" in t for t in titles)


def test_trends_and_quiz_endpoints_respond(client):
    c, _ = client
    trends = c.get("/api/trends", params={"window": "24h"}).json()
    assert "terms" in trends and "topics" in trends
    assert c.get("/api/trends", params={"window": "1y"}).status_code == 400
    quiz = c.get("/api/quiz").json()
    assert quiz["id"].endswith("-r1")


def test_quiz_results_validation(client):
    c, _ = client
    assert c.post("/api/quiz/results", json={"quiz_id": "q", "score": 9, "total": 8}).status_code == 400
    assert c.post("/api/quiz/results", json={"quiz_id": "q", "score": 6, "total": 8}).status_code == 200
    assert c.get("/api/quiz/results").json()[0]["score"] == 6


def test_discussion_only_for_threads(client):
    c, ids = client
    assert c.get(f"/api/stories/{ids['a1']}/discussion").status_code == 400
    assert c.get("/api/stories/missing/discussion").status_code == 404
