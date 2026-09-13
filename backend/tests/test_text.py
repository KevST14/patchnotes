from app.text import (
    canonical_url,
    clean_summary,
    content_tokens,
    extract_terms,
    html_to_paragraphs,
    is_junk_title,
)


def test_canonical_url_strips_tracking_and_noise():
    a = canonical_url("https://www.Example.com/story/?utm_source=rss&utm_medium=feed#comments")
    b = canonical_url("http://example.com/story")
    assert a == b == "https://example.com/story"


def test_canonical_url_keeps_meaningful_query_params():
    assert canonical_url("https://news.ycombinator.com/item?id=123&ref=hn") == "https://news.ycombinator.com/item?id=123"


def test_clean_summary_removes_html_and_feed_boilerplate():
    raw = "<p>Big <b>news</b> today.</p><p>The post Big news appeared first on Some Blog.</p>"
    assert clean_summary(raw) == "Big news today."


def test_clean_summary_truncates_on_a_word_boundary():
    text = clean_summary("word " * 200, max_len=40)
    assert text.endswith("…")
    assert len(text) <= 41
    assert "wor…" not in text


def test_html_to_paragraphs_splits_and_unescapes():
    assert html_to_paragraphs("<p>First &amp; best</p><p>Second <i>one</i></p>") == ["First & best", "Second one"]


def test_extract_terms_keeps_product_names_and_bigrams():
    terms = extract_terms("Nvidia debuts DGX Spark amid the RAMpocalypse")
    assert terms["nvidia"] == "Nvidia"
    assert terms["dgx spark"] == "DGX Spark"
    assert "debuts" in terms  # not filler; trends decide later whether it counts
    assert "the" not in terms


def test_extract_terms_allows_number_tails_but_not_bare_numbers():
    terms = extract_terms("iOS 27 breaks muscle memory on iPhone 17")
    assert "iphone 17" in terms
    assert "ios 27" in terms
    assert "17" not in terms and "27" not in terms


def test_content_tokens_drop_filler_and_stem():
    assert content_tokens("Apple announces new chips for MacBooks") == ["apple", "chip", "macbook"]


def test_junk_titles_are_caught():
    assert is_junk_title("Dyson Promo Codes: 25% Off in October 2026")
    assert is_junk_title("Deals: M5 MacBook Air, MacBook Pro, more")
    assert is_junk_title("The Best Early Prime Day Deals Ahead of Amazon’s Second Sale")
    assert not is_junk_title("Amazon and Synopsys ink billion-dollar deal on AI chip design")
    assert not is_junk_title("Texas school district approves $11M iPad deal")
