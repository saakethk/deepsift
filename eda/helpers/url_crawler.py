"""
Recursive URL crawler with keyword filtering.

Given a starting URL, recursively discovers all links on the page
and only follows/keeps links whose URL path or anchor text matches
configurable keywords. Stays within the same domain by default.

Usage:
    from url_crawler import crawl

    # Default keywords target career/resume pages
    all_urls = crawl("https://www.aamu.edu", max_depth=2)

    # Custom keywords
    all_urls = crawl("https://www.aamu.edu", max_depth=2,
                     keywords=["scholarship", "financial-aid", "tuition"])

    for url in sorted(all_urls):
        print(url)
"""

from __future__ import annotations

import logging
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Default headers so we don't get blocked by basic bot detection
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Default keywords related to career services and resume resources
DEFAULT_KEYWORDS = [
    "career",
    "resume",
    "cv",
    "cover-letter",
    "cover_letter",
    "coverletter",
    "job",
    "employment",
    "hire",
    "hiring",
    "intern",
    "internship",
    "professional-development",
    "career-services",
    "career-center",
    "career_services",
    "career_center",
    "handshake",
    "template",
]


def _url_matches_keywords(url: str, anchor_text: str, keywords: list[str]) -> bool:
    """Check if a URL path or its anchor text contains any of the keywords."""
    url_lower = urlparse(url).path.lower()
    anchor_lower = anchor_text.lower()
    return any(kw in url_lower or kw in anchor_lower for kw in keywords)


def _extract_links(
    html: str, base_url: str, keywords: list[str] | None = None
) -> tuple[set[str], set[str]]:
    """
    Parse HTML and return discovered URLs.

    Returns:
        A tuple of (matching_links, all_links):
        - matching_links: URLs that match the keyword filter (followed + kept)
        - all_links: every URL found on the page (for reference)
    """
    soup = BeautifulSoup(html, "html.parser")
    matching = set()
    all_links = set()

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        # Skip anchors, javascript, mailto, tel links
        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        # Resolve relative URLs against the base
        absolute = urljoin(base_url, href)
        # Strip fragments
        absolute = absolute.split("#")[0]
        if not absolute:
            continue

        all_links.add(absolute)

        # If no keywords, keep everything (original behavior)
        if keywords is None:
            matching.add(absolute)
        else:
            anchor_text = tag.get_text(strip=True)
            if _url_matches_keywords(absolute, anchor_text, keywords):
                matching.add(absolute)

    return matching, all_links


def crawl(
    start_url: str,
    max_depth: int = 2,
    same_domain: bool = True,
    delay: float = 0.5,
    timeout: int = 10,
    max_pages: int = 200,
    keywords: list[str] | None = DEFAULT_KEYWORDS,
) -> set[str]:
    """
    Recursively crawl starting from `start_url` and return discovered URLs
    that match the keyword filter.

    The crawler follows ALL same-domain links to explore the site structure,
    but only *returns* URLs whose path or anchor text matches a keyword.
    This way it can navigate through generic pages (e.g. "Students" ->
    "Student Services" -> "Career Center") to find relevant pages.

    Args:
        start_url:   The URL to start crawling from.
        max_depth:   How many levels deep to follow links (0 = just extract
                     links from the start page, don't follow them).
        same_domain: If True, only follow links on the same domain as start_url.
        delay:       Seconds to wait between requests (be polite).
        timeout:     Request timeout in seconds.
        max_pages:   Safety cap — stop after visiting this many pages.
        keywords:    List of keywords to filter results by. Only URLs whose
                     path or anchor text contains a keyword are included in
                     the returned set. The crawler still follows all links
                     for exploration. Defaults to career/resume keywords.
                     Set to None to return everything.

    Returns:
        A set of discovered URLs matching the keywords.
    """
    start_domain = urlparse(start_url).netloc
    visited: set[str] = set()
    all_discovered: set[str] = {start_url}
    matched: set[str] = set()  # only URLs matching keywords
    queue: list[tuple[str, int]] = [(start_url, 0)]  # (url, current_depth)

    if keywords is not None:
        logger.info("Filtering results with keywords: %s", keywords)

    while queue:
        if len(visited) >= max_pages:
            logger.warning(
                "Reached max pages cap (%d). Stopping crawl early.", max_pages
            )
            break

        url, depth = queue.pop(0)

        if url in visited:
            continue
        visited.add(url)

        # Check if current URL matches keywords
        if keywords is None or _url_matches_keywords(url, "", keywords):
            matched.add(url)

        # Only fetch pages we haven't visited
        try:
            logger.info("Depth %d | Crawling: %s", depth, url)
            resp = requests.get(
                url, headers=_DEFAULT_HEADERS, timeout=timeout, allow_redirects=True
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Failed to fetch %s: %s", url, e)
            continue

        # Only parse HTML responses
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            continue

        # Extract ALL links for exploration, and matching links for results
        matching_links, all_links = _extract_links(resp.text, url, keywords)

        # Add keyword-matching links to the results set
        for link in matching_links:
            if same_domain and urlparse(link).netloc != start_domain:
                continue
            matched.add(link)

        # Enqueue ALL same-domain links for exploration (not just matching)
        for link in all_links:
            if link in all_discovered:
                continue

            if same_domain and urlparse(link).netloc != start_domain:
                continue

            all_discovered.add(link)

            # Only enqueue if we haven't hit max depth
            if depth < max_depth:
                queue.append((link, depth + 1))

        # Rate-limit to be respectful
        time.sleep(delay)

    logger.info(
        "Crawl complete. Visited %d pages, found %d matching URLs "
        "(out of %d total discovered).",
        len(visited),
        len(matched),
        len(all_discovered),
    )
    return matched


if __name__ == "__main__":
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.aamu.edu"
    depth = int(sys.argv[2]) if len(sys.argv) > 2 else 2

    results = crawl(url, max_depth=depth)
    print(f"\n{'='*60}")
    print(f"Found {len(results)} matching URLs:")
    print(f"{'='*60}")
    for u in sorted(results):
        print(u)
