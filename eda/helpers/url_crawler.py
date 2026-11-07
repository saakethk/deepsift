"""
Async recursive URL crawler.

Given a starting URL, concurrently discovers all links and returns
discovered URLs. Optionally filters by configurable keywords in the URL
path or anchor text. Uses asyncio + aiohttp for parallelism and a
priority queue.

Usage (sync wrapper — works in notebooks and scripts):
    from url_crawler import crawl

    # Crawl without keyword filtering (returns all discovered URLs)
    urls = crawl("https://www.aamu.edu", max_depth=3)

    # Optional keyword filtering
    urls = crawl("https://www.aamu.edu", max_depth=3,
                 keywords=["career", "resume"])

    # Crawl multiple schools at once
    from url_crawler import crawl_batch
    results = crawl_batch(["https://www.aamu.edu", "https://www.harvard.edu"])
"""

from __future__ import annotations

import asyncio
import heapq
from urllib.parse import urljoin, urlparse
import aiohttp
from bs4 import BeautifulSoup

# Default headers so we don't get blocked by basic bot detection
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _url_matches_keywords(url: str, anchor_text: str, keywords: list[str]) -> bool:
    """Check if a URL path or its anchor text contains any of the keywords."""
    url_lower = urlparse(url).path.lower()
    anchor_lower = anchor_text.lower()
    return any(kw in url_lower or kw in anchor_lower for kw in keywords)


def _priority_score(url: str, keywords: list[str]) -> int:
    """
    Lower score = higher priority.
    URLs containing keywords are crawled first when keywords are provided.
    """
    if not keywords:
        return 0
    path = urlparse(url).path.lower()
    if any(kw in path for kw in keywords):
        return 0  # highest priority — likely relevant
    return 1  # standard priority



def _extract_links(
    html: str, base_url: str, keywords: list[str] | None = None
) -> tuple[set[str], set[str]]:
    """
    Parse HTML and return (matching_links, all_followable_links).

    matching_links:  URLs whose path or anchor text contains a keyword
    all_followable:  all same-scheme links that aren't excluded by path
    """
    soup = BeautifulSoup(html, "html.parser")
    matching = set()
    followable = set()

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        absolute = urljoin(base_url, href).split("#")[0]
        if not absolute or not absolute.startswith("http"):
            continue

        followable.add(absolute)

        if keywords is None:
            matching.add(absolute)
        else:
            anchor_text = tag.get_text(strip=True)
            if _url_matches_keywords(absolute, anchor_text, keywords):
                matching.add(absolute)

    return matching, followable


async def _fetch(
    session: aiohttp.ClientSession, url: str, timeout: int
) -> str | None:
    """Fetch a URL and return HTML content, or None on failure."""
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=timeout), allow_redirects=True
        ) as resp:
            if resp.status != 200:
                return None
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                return None
            return await resp.text(errors="replace")
    except Exception:
        return None


async def _crawl_async(
    start_url: str,
    max_depth: int = 3,
    same_domain: bool = True,
    concurrency: int = 10,
    timeout: int = 10,
    max_pages: int = 200,
    keywords: list[str] | None = None,
) -> set[str]:
    """Core async crawler. See `crawl()` for parameter docs."""
    start_domain = urlparse(start_url).netloc.lower()
    visited: set[str] = set()
    all_discovered: set[str] = {start_url}
    matched: set[str] = set()

    # Priority queue: (priority, counter, url, depth)
    counter = 0
    pq: list[tuple[int, int, str, int]] = []
    heapq.heappush(pq, (0, counter, start_url, 0))

    sem = asyncio.Semaphore(concurrency)

    kw_list = keywords or []

    async with aiohttp.ClientSession(headers=_DEFAULT_HEADERS) as session:
        while pq:
            if len(visited) >= max_pages:
                break

            # Grab a batch of URLs up to the concurrency limit
            batch: list[tuple[str, int]] = []
            while pq and len(batch) < concurrency:
                _, _, url, depth = heapq.heappop(pq)
                if url not in visited:
                    batch.append((url, depth))

            if not batch:
                break

            # Fetch all pages in the batch concurrently
            async def process(url: str, depth: int):
                async with sem:
                    visited.add(url)

                    # Check if current URL matches keywords
                    if keywords is None or _url_matches_keywords(url, "", kw_list):
                        matched.add(url)

                    html = await _fetch(session, url, timeout)
                    if html is None:
                        return

                    matching_links, all_links = _extract_links(
                        html, url, keywords
                    )

                    # Collect keyword-matching links
                    for link in matching_links:
                        link_domain = urlparse(link).netloc.lower()
                        if same_domain and link_domain != start_domain:
                            continue
                        matched.add(link)

                    # Enqueue all followable links for exploration
                    if depth < max_depth:
                        nonlocal counter
                        for link in all_links:
                            if link in all_discovered:
                                continue
                            link_domain = urlparse(link).netloc.lower()
                            if same_domain and link_domain != start_domain:
                                continue
                            all_discovered.add(link)
                            prio = _priority_score(link, kw_list)
                            counter += 1
                            heapq.heappush(pq, (prio, counter, link, depth + 1))

            await asyncio.gather(*(process(u, d) for u, d in batch))

    return matched


def crawl(
    start_url: str,
    max_depth: int = 3,
    same_domain: bool = True,
    concurrency: int = 10,
    timeout: int = 10,
    max_pages: int = 200,
    keywords: list[str] | None = None,
) -> set[str]:
    """
    Crawl a website and return discovered URLs.

    Explores the same-domain site tree concurrently. If keywords are provided,
    only returns URLs whose path or anchor text contains at least one keyword,
    prioritizing them in the crawl. If keywords is None (default), returns all
    discovered URLs.

    Args:
        start_url:    The URL to start crawling from.
        max_depth:    How many levels deep to follow links.
        same_domain:  If True, only follow links on the same domain.
        concurrency:  Max number of simultaneous HTTP requests.
        timeout:      Request timeout in seconds per page.
        max_pages:    Safety cap — stop after visiting this many pages.
        keywords:     Optional list of keywords to filter results.
                      If None (default), returns all discovered URLs.

    Returns:
        A set of discovered URLs.
    """
    # Handle running inside an existing event loop (e.g. Jupyter)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're in Jupyter or similar — use nest_asyncio or run in thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                _crawl_async(
                    start_url, max_depth, same_domain, concurrency,
                    timeout, max_pages, keywords,
                ),
            )
            return future.result()
    else:
        return asyncio.run(
            _crawl_async(
                start_url, max_depth, same_domain, concurrency,
                timeout, max_pages, keywords,
            )
        )


def crawl_batch(
    urls: list[str],
    max_depth: int = 3,
    concurrency_per_site: int = 10,
    timeout: int = 10,
    max_pages: int = 200,
    keywords: list[str] | None = None,
) -> dict[str, set[str]]:
    """
    Crawl multiple websites and return results keyed by start URL.

    Each site is crawled sequentially (to avoid hammering many servers
    at once), but pages within each site are fetched concurrently.

    Args:
        urls:                 List of starting URLs to crawl.
        max_depth:            How many levels deep per site.
        concurrency_per_site: Max simultaneous requests per site.
        timeout:              Request timeout per page.
        max_pages:            Max pages to visit per site.
        keywords:             Keyword filter (see crawl()).

    Returns:
        Dict mapping each start_url to its set of matched URLs.
    """
    results = {}
    for url in urls:
        try:
            results[url] = crawl(
                url, max_depth, True, concurrency_per_site,
                timeout, max_pages, keywords,
            )
        except Exception:
            results[url] = set()
    return results


if __name__ == "__main__":
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.aamu.edu"
    depth = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    results = crawl(url, max_depth=depth)
    print(f"\n{'='*60}")
    print(f"Found {len(results)} matching URLs:")
    print(f"{'='*60}")
    for u in sorted(results):
        print(u)
