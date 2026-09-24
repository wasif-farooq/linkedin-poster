from app.schemas.post import Draft, Scores
from app.tools.post_rules import check_post

GOOD_BODY = "\n\n".join(
    [
        "Your agent instructions are production config now.",
        "Claude Code reads AGENTS.md when a folder has no CLAUDE.md.",
        "That makes one file the shared source of truth for every coding agent you run.",
        "Here's what I'd do:\n→ Version it\n→ Review it like code\n→ Test what each agent loads",
        "Which agents does your team run today?",
    ]
)
TAGS = ["#AIEngineering", "#ClaudeCode", "#DevTools"]


def check(body=GOOD_BODY, tags=TAGS, **kw):
    return check_post(Draft(text=body, hashtags=tags), target_min=100, target_max=1800, **kw)


def test_clean_post_passes():
    report = check()
    assert report.ok and report.warnings == []


def test_over_linkedin_limit_is_error():
    assert any("limit is 3000" in e for e in check(body="word " * 700).errors)


def test_markdown_is_error_but_list_markers_only_warn():
    report = check(body="**Bold** hook\n\n## Heading\n\nSee [docs](https://x.dev)\n\n- item")
    assert len(report.errors) == 3
    assert any("list markers" in w for w in report.warnings)


def test_warnings():
    long_hook = "x" * 250
    report = check(
        body=f"{long_hook}\n\nRead https://x.dev #inline\n\n" + "y " * 200, tags=["#One"]
    )
    text = " ".join(report.warnings)
    for fragment in ("hook", "hashtags; use 3-5", "Hashtags in the body", "URL", "paragraph"):
        assert fragment in text, fragment


def test_empty_post():
    assert check(body="   ").errors == ["Post is empty."]


def test_hashtags_normalized_and_deduped():
    d = Draft(
        text="t", hashtags=["AI Engineering", "#ai-engineering", "#ClaudeCode", "##", "claudecode"]
    )
    assert d.hashtags == ["#AIEngineering", "#ClaudeCode"]  # case-insensitive dedupe


def test_full_text_appends_hashtags():
    assert Draft(text=" body \n", hashtags=["#A"]).full_text() == "body\n\n#A"
    assert Draft(text="body", hashtags=[]).full_text() == "body"


def test_scores_lowest():
    s = Scores(hook=8, insight=6, accuracy=9, clarity=7, tone=9)
    assert s.lowest() == ("insight", 6)
