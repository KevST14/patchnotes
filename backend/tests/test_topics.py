from app.topics import classify


def test_headline_keyword_tags_topic():
    assert classify("OpenAI launches always-on agents")[0] == "ai"


def test_single_summary_mention_is_not_enough():
    assert "crypto" not in classify("A new phone", "It does not support bitcoin wallets.")


def test_two_summary_mentions_are_enough():
    assert "crypto" in classify("A new phone", "A bitcoin wallet. Also ethereum.")


def test_source_tags_count():
    assert "dev" in classify("Lists that keep track of their reversal", source_tags=["programming"])


def test_free_form_categories_match_keywords():
    assert "ai" in classify("Something happened", source_tags=["Artificial Intelligence"])


def test_strongest_topic_first():
    topics = classify("Ransomware gang hacks Nvidia, leaks GPU driver source code")
    assert topics[0] == "security"
    assert "hardware" in topics


def test_word_boundaries():
    # "said" contains "ai" and "rain" contains "ai"; neither should tag AI.
    assert "ai" not in classify("Officials said rain delayed the launch")
