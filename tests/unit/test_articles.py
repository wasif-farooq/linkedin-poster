import httpx
import respx

from app.tools.sources.articles import _truncate, fetch_article, fetch_articles

PARAGRAPH = (
    "Agent instruction files are becoming shared infrastructure for engineering teams. "
    "When several coding agents read the same file, its contents deserve code review. "
)
HTML = f"""<html><head><title>Agents as config</title>
<meta property="article:published_time" content="2026-09-21"></head>
<body><nav>menu</nav><article><h1>Agents as config</h1>
<p>{PARAGRAPH * 3}</p><p>{PARAGRAPH * 3}</p></article><footer>footer</footer></body></html>"""


@respx.mock
def test_extracts_main_text_and_metadata():
    respx.get("https://ex.com/post").mock(
        return_value=httpx.Response(200, text=HTML, headers={"content-type": "text/html"})
    )
    article = fetch_article("https://ex.com/post")
    assert article is not None
    assert "shared infrastructure" in article.text
    assert "menu" not in article.text
    assert article.title == "Agents as config"


@respx.mock
def test_truncates_to_max_chars():
    respx.get("https://ex.com/post").mock(
        return_value=httpx.Response(200, text=HTML, headers={"content-type": "text/html"})
    )
    article = fetch_article("https://ex.com/post", max_chars=300)
    assert len(article.text) <= 302 and article.text.endswith("…")


def test_skips_unreadable_hosts():
    assert fetch_article("https://x.com/someone/status/1") is None
    assert fetch_article("https://news.ycombinator.com/item?id=1") is None


@respx.mock
def test_non_html_short_and_errors_return_none():
    respx.get("https://ex.com/file.pdf").mock(
        return_value=httpx.Response(
            200, content=b"%PDF", headers={"content-type": "application/pdf"}
        )
    )
    respx.get("https://ex.com/short").mock(
        return_value=httpx.Response(200, text="<p>tiny</p>", headers={"content-type": "text/html"})
    )
    respx.get("https://ex.com/gone").mock(return_value=httpx.Response(404))
    assert fetch_article("https://ex.com/file.pdf") is None
    assert fetch_article("https://ex.com/short") is None
    assert fetch_article("https://ex.com/gone") is None


@respx.mock
def test_fetch_articles_keeps_only_successes():
    respx.get("https://ex.com/post").mock(
        return_value=httpx.Response(200, text=HTML, headers={"content-type": "text/html"})
    )
    respx.get("https://ex.com/gone").mock(return_value=httpx.Response(500))
    assert list(fetch_articles(["https://ex.com/post", "https://ex.com/gone"])) == [
        "https://ex.com/post"
    ]


def test_truncate_on_word_boundary():
    assert _truncate("one two three", 8) == "one two …"
    assert _truncate("short", 10) == "short"
