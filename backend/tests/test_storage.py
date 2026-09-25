import pytest

from .helpers import make_story


def test_upsert_counts_new_and_refreshes_score(storage):
    s = make_story(source="hn", native_id="1", url="https://x/1", score=10, comments=1)
    assert storage.upsert_stories([s]) == 1
    assert storage.upsert_stories([{**s, "score": 250, "comments": 80}]) == 0
    stored = storage.get_story(s["id"])
    assert stored["score"] == 250 and stored["comments"] == 80
    assert stored["topics"] == s["topics"]


def test_upsert_keeps_existing_image_when_feed_drops_it(storage):
    s = make_story(native_id="1", url="https://x/1", image="https://img/1.jpg")
    storage.upsert_stories([s])
    storage.upsert_stories([{**s, "image": None}])
    assert storage.get_story(s["id"])["image"] == "https://img/1.jpg"


def test_prune_keeps_saved_stories(storage):
    old = make_story(native_id="old", url="https://x/old", published_at=1000)
    kept = make_story(native_id="kept", url="https://x/kept", published_at=1000)
    storage.upsert_stories([old, kept])
    storage.save_story(kept["id"])
    assert storage.prune_stories(older_than_ts=5000) == 1
    assert storage.get_story(kept["id"]) is not None


def test_undo_removes_latest_triage_and_unsaves(storage):
    s = make_story(native_id="1", url="https://x/1")
    storage.upsert_stories([s])
    storage.record_interaction(s["id"], "open")
    storage.record_interaction(s["id"], "save")
    storage.save_story(s["id"])
    assert storage.undo_last_interaction(s["id"]) == "save"
    assert s["id"] not in storage.saved_ids()
    assert storage.story_actions()[s["id"]] == {"open"}  # opens aren't undone
    assert storage.undo_last_interaction(s["id"]) is None


def test_unknown_action_rejected(storage):
    with pytest.raises(ValueError):
        storage.record_interaction("x", "like")


def test_prefs_round_trip_and_validation(storage):
    assert storage.get_prefs()["followed_topics"] == []
    storage.set_prefs({"followed_topics": ["ai"], "muted_terms": ["crypto"]})
    prefs = storage.get_prefs()
    assert prefs["followed_topics"] == ["ai"] and prefs["muted_terms"] == ["crypto"]
    with pytest.raises(ValueError):
        storage.set_prefs({"theme": "dark"})


def test_source_status_remembers_etag_across_failures(storage):
    storage.record_source_attempt("ars", ok=True, item_count=20, etag='"abc"')
    storage.record_source_attempt("ars", ok=False, error="timeout")
    status = storage.get_source_status()["ars"]
    assert status["etag"] == '"abc"'
    assert status["last_error"] == "timeout"
    assert status["last_success"] is not None
    assert status["item_count"] == 20


def test_undo_takes_back_a_hide(storage):
    s = make_story(native_id="h", url="https://x/h")
    storage.upsert_stories([s])
    storage.record_interaction(s["id"], "hide")
    assert storage.undo_last_interaction(s["id"]) == "hide"
    assert s["id"] not in storage.story_actions()
