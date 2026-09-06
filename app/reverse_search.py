"""Genuine reverse-image search via SerpApi's Google Lens engine.

This hits Google Lens live through SerpApi. Nothing here is cached, stubbed or
seeded: if Lens finds no matching social media post, this module returns an
empty list and the pipeline stops. Inventing a plausible-looking URL would
defeat the entire point of anchoring the result on a blockchain.

Two operational notes, both discovered against the live API:

  * The `type` parameter is REQUIRED. Google changed the Lens layout, and a
    request without it comes back carrying only an `ai_overview` and no match
    lists whatsoever.

  * Lens can only search a publicly reachable image URL; it cannot accept
    uploaded bytes. The input photo is deliberately NOT auto-uploaded to an
    image host to work around that -- publishing a person's face to a third
    party without consent is not a reasonable default. The operator supplies a
    URL for an image that is already public, and the pipeline independently
    confirms that URL shows the same face before searching.
"""
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import SERPAPI_KEY

SERPAPI_ENDPOINT = "https://serpapi.com/search"

# Hosts we count as "social media" for the task requirement.
SOCIAL_DOMAINS = frozenset(
    {
        "x.com", "twitter.com", "t.co",
        "instagram.com",
        "facebook.com", "fb.com",
        "linkedin.com",
        "reddit.com", "redd.it",
        "tiktok.com",
        "youtube.com", "youtu.be",
        "threads.net", "threads.com",
        "tumblr.com",
        "vk.com",
        "weibo.com", "weibo.cn",
        "flickr.com",
        "bsky.app",
        "snapchat.com",
        "twitch.tv",
        "medium.com",
        "quora.com",
    }
)

# Brands with many country TLDs (pinterest.co.uk, mastodon.social, ...).
SOCIAL_BRANDS = frozenset({"pinterest", "mastodon"})


def social_host(url: str) -> str | None:
    """Return the social domain this URL belongs to, or None.

    Matches the host itself and any subdomain of it, so `www.x.com` and
    `mobile.twitter.com` both count, while `x.com.evil.net` does not.
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return None
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]

    for domain in SOCIAL_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return domain

    # pinterest.co.uk, mastodon.social, etc.
    labels = host.split(".")
    for i, label in enumerate(labels):
        if label in SOCIAL_BRANDS and i < len(labels) - 1:
            return ".".join(labels[i:])
    return None


async def search_lens(image_url: str | None) -> dict[str, Any]:
    """Query Google Lens through SerpApi for pages showing this image."""
    if not SERPAPI_KEY:
        return {
            "provider": "serpapi_google_lens",
            "available": False,
            "reason": "SERPAPI_KEY not set in .env",
            "results": [],
        }
    if not image_url:
        return {
            "provider": "serpapi_google_lens",
            "available": False,
            "reason": (
                "no public image_url supplied; Google Lens cannot search local "
                "bytes, and the input photo is deliberately not auto-uploaded to "
                "a third-party host"
            ),
            "results": [],
        }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(
            SERPAPI_ENDPOINT,
            params={
                "engine": "google_lens",
                "url": image_url,
                "api_key": SERPAPI_KEY,
                "hl": "en",
                # Required -- see the module docstring.
                "type": "visual_matches",
            },
        )

    if resp.status_code != 200:
        return {
            "provider": "serpapi_google_lens",
            "available": False,
            "reason": f"HTTP {resp.status_code}: {resp.text[:200]}",
            "results": [],
        }

    data = resp.json()
    if "error" in data:
        # Lens finding nothing is a normal outcome, not a transport failure.
        return {
            "provider": "serpapi_google_lens",
            "available": True,
            "reason": str(data["error"])[:200],
            "results": [],
        }

    results: list[dict[str, Any]] = []
    for key in ("exact_matches", "visual_matches"):
        for m in data.get(key, []):
            results.append(
                {
                    "url": m.get("link", ""),
                    "page_title": (m.get("title") or m.get("source") or "").strip(),
                    "match_type": f"google_lens/{key}",
                    "provider": "serpapi_google_lens",
                }
            )

    return {"provider": "serpapi_google_lens", "available": True, "results": results}


def filter_social(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only results hosted on a social platform, preserving result order."""
    social: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in results:
        host = social_host(r.get("url", ""))
        if host and r["url"] not in seen:
            seen.add(r["url"])
            social.append({**r, "host": host})
    return social


async def find_social_match(image_url: str | None = None) -> dict[str, Any]:
    """Search Lens and return every genuine social-media hit.

    Returns an empty `social` list when nothing matched. That is a valid,
    expected outcome -- the caller must not fabricate a substitute.
    """
    lens = await search_lens(image_url)
    social = filter_social(lens["results"])

    return {
        "social": social,
        "meta": {
            "providers_tried": [lens["provider"]],
            "total_results": len(lens["results"]),
            "social_results": len(social),
            "provider_status": [
                {
                    "provider": lens["provider"],
                    "available": lens["available"],
                    "results": len(lens["results"]),
                    "reason": lens.get("reason"),
                }
            ],
        },
    }
