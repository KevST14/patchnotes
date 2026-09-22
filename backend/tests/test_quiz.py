import random

from app import ranking
from app.quiz import build_quiz, make_blank, number_distractors, _NUMBER_RE

from .helpers import NOW, make_story

HEADLINES = [
    ("ars", "Micron says the RAM shortage will last through 2028"),
    ("verge", "Google breaks its promise of ten years of Chromebook updates"),
    ("register", "OpenAI shows three staff the door over alleged information misuse"),
    ("tomshw", "Nvidia debuts $4,999 DGX Spark with half the RAM and storage"),
    ("engadget", "Apple quietly raises the price of the Mac mini in Europe"),
    ("wired", "Microsoft makes Windows settings backup the default for everyone"),
    ("bleeping", "Fortinet warns of a critical FortiMail flaw exploited in attacks"),
    ("9to5mac", "Samsung and Intel team up on a new memory packaging plant"),
    ("techcrunch", "Amazon and Anthropic expand their cloud computing partnership again"),
    ("404media", "Meta's Muse agent ignores the permissions users set for it"),
    ("techreview", "Tesla's robotaxi pilot expands to three more cities next month"),
]


def _stories():
    stories = [
        make_story(source=src, native_id=f"{src}-{i}", url=f"https://{src}/{i}", title=title, published_at=NOW - (i + 1) * 3600)
        for i, (src, title) in enumerate(HEADLINES)
    ]
    stories += [
        make_story(source="hn", native_id=f"hn{i}", url=f"https://hn/{i}", title=f"Show HN: a small tool number {i} for people", score=score, published_at=NOW - 3600)
        for i, score in enumerate([1200, 300, 150, 90, 60])
    ]
    for s in stories:
        s["cluster_id"] = s["id"]
    return stories


def _quiz(quiz_id="2026-10-02-r1", seen=frozenset()):
    stories = _stories()
    clusters = ranking.build_clusters(stories, ranking.popularity_table(stories), NOW)
    return build_quiz(quiz_id, stories, clusters, set(seen))


def test_quiz_is_deterministic_per_id():
    assert _quiz()["questions"] == _quiz()["questions"]
    assert _quiz()["questions"] != _quiz("2026-10-02-r2")["questions"]


def test_every_question_has_four_distinct_options_and_a_valid_answer():
    quiz = _quiz()
    assert len(quiz["questions"]) == 8
    for q in quiz["questions"]:
        assert len(q["options"]) == 4
        assert len(set(o.lower() for o in q["options"])) == 4
        assert 0 <= q["answer"] < 4


def test_blank_questions_hide_the_answer():
    for q in _quiz()["questions"]:
        if q["type"] == "blank":
            assert "_____" in q["headline"]
            answer = q["options"][q["answer"]]
            assert answer not in q["headline"]
            assert q["headline"].replace("_____", answer) in q["story"]["title"].replace("’", "'")


def test_hn_question_answer_has_most_points():
    q = next(q for q in _quiz()["questions"] if q["type"] == "hn")
    points = [int(v.split()[0].replace(",", "")) for v in q["option_values"]]
    assert points[q["answer"]] == max(points)


def test_company_blanks_get_company_distractors():
    rng = random.Random(1)
    story = make_story(source="register", native_id="x", url="https://x", title="OpenAI shows three staff the door over alleged information misuse")
    pool = {"company": ["Google", "Micron", "Nvidia", "Apple"], "product": [], "person": []}
    q = make_blank(story, pool, rng)
    assert q["options"][q["answer"]] == "OpenAI"
    assert all(o in {"OpenAI", "Google", "Micron", "Nvidia", "Apple"} for o in q["options"])


def test_number_distractors_keep_the_format():
    match = _NUMBER_RE.search("Nvidia debuts $4,999 DGX Spark")
    options = number_distractors(match, random.Random(3))
    assert len(options) == 3
    assert all(o.startswith("$") and "," in o for o in options)
    assert "$4,999" not in options


def test_bare_small_numbers_are_not_asked():
    match = _NUMBER_RE.search("Three reasons: 3 new features in iOS")
    assert number_distractors(match, random.Random(1)) is None
