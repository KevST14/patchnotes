from app.fetchers import parse_feed, parse_github, parse_hn_hits, parse_lobsters

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel><title>Example</title>
<item>
  <title>Nvidia Shield TV is now $100 more expensive</title>
  <link>https://example.com/shield?utm_source=rss</link>
  <guid>https://example.com/?p=1</guid>
  <dc:creator>Ryan</dc:creator>
  <pubDate>Fri, 02 Oct 2026 14:52:16 +0000</pubDate>
  <category>NVIDIA</category>
  <description><![CDATA[<p>Initially launched in 2019.</p>]]></description>
  <media:thumbnail url="https://example.com/thumb.jpg" />
</item>
<item><title></title><link>https://example.com/empty</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom</title>
<entry>
  <title type="html"><![CDATA[Dots get up in Muse&#8217;s business]]></title>
  <link rel="alternate" href="https://example.org/dots" />
  <id>https://example.org/?p=9</id>
  <published>2026-10-02T11:47:05-04:00</published>
  <content type="html"><![CDATA[<figure><img src="https://example.org/img.jpg" /></figure><p>OpenAI's answer.</p>]]></content>
</entry>
</feed>"""


def test_parse_rss_item():
    [story] = parse_feed("ars", RSS)
    assert story["title"] == "Nvidia Shield TV is now $100 more expensive"
    assert story["native_id"] == "https://example.com/?p=1"
    assert story["author"] == "Ryan"
    assert story["summary"] == "Initially launched in 2019."
    assert story["image"] == "https://example.com/thumb.jpg"
    assert story["source_tags"] == ["NVIDIA"]
    assert story["published_at"] == 1790952736.0  # 2026-10-02T14:52:16Z


def test_parse_atom_entry_with_image_in_content():
    [story] = parse_feed("verge", ATOM)
    assert story["title"] == "Dots get up in Muse’s business"
    assert story["image"] == "https://example.org/img.jpg"
    assert story["summary"] == "OpenAI's answer."


def test_parse_hn_hits_handles_ask_hn_without_url():
    stories = parse_hn_hits(
        [
            {"objectID": "1", "title": "Pi 1.0", "url": "https://pi.dev", "points": 1500, "num_comments": 500, "created_at_i": 100, "author": "a"},
            {"objectID": "2", "title": "Ask HN: Who is hiring?", "url": None, "points": 300, "num_comments": 900, "created_at_i": 200, "story_text": "<p>Post below</p>"},
            {"objectID": "3", "title": ""},
        ]
    )
    assert [s["native_id"] for s in stories] == ["1", "2"]
    assert stories[0]["url"] == "https://pi.dev"
    assert stories[0]["discussion_url"] == "https://news.ycombinator.com/item?id=1"
    assert stories[1]["url"] == stories[1]["discussion_url"]
    assert stories[1]["summary"] == "Post below"


def test_parse_lobsters():
    [story] = parse_lobsters(
        [
            {
                "short_id": "gmjegm",
                "created_at": "2026-10-01T21:17:04.275-05:00",
                "title": "Waterfox adds a feed reader",
                "url": "https://waterfox.com/r",
                "score": 42,
                "comment_count": 11,
                "description": "",
                "submitter_user": "chai",
                "tags": ["browsers", "release"],
                "short_id_url": "https://lobste.rs/s/gmjegm",
                "comments_url": "https://lobste.rs/s/gmjegm/waterfox",
            }
        ]
    )
    assert story["discussion_url"] == "https://lobste.rs/s/gmjegm/waterfox"
    assert story["source_tags"] == ["browsers", "release"]
    assert story["author"] == "chai"
    assert story["score"] == 42


def test_parse_github_builds_headline_from_repo():
    [story] = parse_github(
        [
            {
                "id": 7,
                "full_name": "firelex/jeff",
                "description": "Millisecond decisions",
                "html_url": "https://github.com/firelex/jeff",
                "stargazers_count": 900,
                "language": "Python",
                "topics": ["llm"],
                "owner": {"login": "firelex"},
                "created_at": "2026-09-30T10:00:00Z",
            }
        ]
    )
    assert story["title"] == "firelex/jeff: Millisecond decisions"
    assert story["source_tags"] == ["python", "llm"]
    assert story["extra"]["language"] == "Python"
