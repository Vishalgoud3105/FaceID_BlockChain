"""Social-domain filtering and no-fabrication guarantees. Offline."""
import asyncio

import pytest

from app import reverse_search as rs


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://x.com/someone/status/1859", "x.com"),
        ("https://www.x.com/someone/status/1859", "x.com"),
        ("https://mobile.twitter.com/a/status/1", "twitter.com"),
        ("https://www.instagram.com/p/CxYz/", "instagram.com"),
        ("https://www.reddit.com/r/pics/comments/abc/", "reddit.com"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtu.be"),
        ("https://in.pinterest.com/pin/123456/", "pinterest.com"),
        ("https://www.pinterest.co.uk/pin/99/", "pinterest.co.uk"),
        ("https://mastodon.social/@user/1234", "mastodon.social"),
        ("https://bsky.app/profile/a.bsky.social/post/1", "bsky.app"),
    ],
)
def test_social_urls_are_recognised(url, expected):
    assert rs.social_host(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://edition.cnn.com/2026/09/01/story",
        "https://en.wikipedia.org/wiki/Face",
        "https://example.com/photo.jpg",
        "",
        "not-a-url",
        "ftp://files.example.com/a.jpg",
    ],
)
def test_non_social_urls_are_rejected(url):
    assert rs.social_host(url) is None


def test_lookalike_domain_is_not_treated_as_social():
    """`x.com.evil.net` must NOT match `x.com` -- suffix matching has to be
    anchored on a label boundary, not a substring."""
    assert rs.social_host("https://x.com.evil.net/phish") is None
    assert rs.social_host("https://notinstagram.com/p/1") is None
    assert rs.social_host("https://fakex.com/a") is None


def test_filter_social_dedupes_and_tags_host():
    results = [
        {"url": "https://x.com/a/status/1", "provider": "p"},
        {"url": "https://x.com/a/status/1", "provider": "p"},  # duplicate
        {"url": "https://cnn.com/story", "provider": "p"},
    ]
    out = rs.filter_social(results)
    assert len(out) == 1
    assert out[0]["host"] == "x.com"


def test_no_hardcoded_match_urls_in_source():
    """The task forbids faked results. No social URL may be baked into the
    module that produces matches -- every URL must come from a live API."""
    src = (rs.__file__)
    text = open(src, encoding="utf-8").read()
    # The only URL allowed as a literal is the API endpoint itself.
    import re

    urls = re.findall(r"https?://[^\s\"')]+", text)
    allowed = {rs.SERPAPI_ENDPOINT}
    offenders = [
        u for u in urls if u not in allowed and rs.social_host(u) is not None
    ]
    assert offenders == [], f"hardcoded social URLs found: {offenders}"


def test_provider_reports_unavailable_without_a_key(monkeypatch):
    """With no credentials the pipeline must return zero matches -- never a
    placeholder result."""
    monkeypatch.setattr(rs, "SERPAPI_KEY", "")

    out = asyncio.run(rs.find_social_match("https://example.com/photo.jpg"))

    assert out["social"] == []
    assert out["meta"]["social_results"] == 0
    assert all(p["available"] is False for p in out["meta"]["provider_status"])


def test_refuses_to_upload_without_a_public_url(monkeypatch):
    """Privacy guard: no auto-upload of the input photo."""
    monkeypatch.setattr(rs, "SERPAPI_KEY", "fake-key-not-used")
    out = asyncio.run(rs.search_lens(None))
    assert out["available"] is False
    assert "auto-uploaded" in out["reason"]
    assert out["results"] == []
