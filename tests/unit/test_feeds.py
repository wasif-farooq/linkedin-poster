from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import respx

from app.tools.sources.feeds import clean_text, fetch_feed, parse_feed

NOW = datetime.now(UTC)
RECENT = format_datetime(NOW - timedelta(days=1))
OLD = format_datetime(NOW - timedelta(days=30))

RSS = f"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Test Blog</title>
  <item><title>Fresh &amp; relevant</title><link>https://ex.com/a</link>
        <description>&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;</description>
        <pubDate>{RECENT}</pubDate></item>
  <item><title>Old post</title><link>https://ex.com/old</link><pubDate>{OLD}</pubDate></item>
  <item><title>No date</title><link>https://ex.com/nodate</link></item>
  <item><title></title><link>https://ex.com/untitled</link></item>
</channel></rss>"""

ATOM = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Site</title>
  <entry><title>Atom entry</title><link href="https://atom.ex/1"/>
         <updated>{(NOW - timedelta(hours=3)).isoformat()}</updated>
         <summary>Short summary</summary></entry>
</feed>"""


def test_parse_rss_filters_old_undated_and_untitled_and_strips_html():
    items = parse_feed(RSS, "https://ex.com/feed", max_age_days=7)
    assert [i.title for i in items] == ["Fresh & relevant"]  # undated could be from 2019
    assert items[0].source == "Test Blog"
    assert items[0].summary == "Hello world"
    assert items[0].published is not None


def test_parse_keeps_the_newest_when_a_feed_lists_oldest_first():
    entries = "".join(
        f"<item><title>Post {h}h</title><link>https://ex.com/{h}</link>"
        f"<pubDate>{format_datetime(NOW - timedelta(hours=h))}</pubDate></item>"
        for h in (50, 30, 10, 2)
    )
    feed = f'<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>{entries}</channel></rss>'
    assert [i.title for i in parse_feed(feed, limit=2)] == ["Post 2h", "Post 10h"]


def test_parse_atom():
    items = parse_feed(ATOM, max_age_days=7)
    assert len(items) == 1
    assert items[0].url == "https://atom.ex/1"
    assert items[0].source == "Atom Site"


def test_parse_respects_limit():
    assert len(parse_feed(RSS, max_age_days=7, limit=1)) == 1


@respx.mock
def test_fetch_feed_success():
    respx.get("https://ex.com/feed").mock(return_value=httpx.Response(200, text=RSS))
    assert len(fetch_feed("https://ex.com/feed")) == 1


@respx.mock
def test_fetch_feed_error_returns_empty():
    respx.get("https://ex.com/feed").mock(return_value=httpx.Response(500))
    assert fetch_feed("https://ex.com/feed") == []


def test_clean_text():
    assert clean_text("<p>a&amp;b</p>\n\n c") == "a&b c"
