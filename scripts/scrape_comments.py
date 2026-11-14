"""
Backwards-compatible interface for comment scraping.
Delegates to the generalized RedditScraper class.
"""
from typing import List, Optional
from scripts.filters import Filters
from scripts.scraper import RedditScraper


def collect_cohort_comments(
    post_ids: List[str],
    output_path: str = "data/curated_comments_5yr.parquet",
    concurrency_limit: int = 5,
    chunk_size: int = 500,
    filters: Optional[Filters] = None,
) -> int:
    scraper = RedditScraper(
        filters=filters or Filters(),
        comment_workers=concurrency_limit,
    )
    return scraper.scrape_comments(
        post_ids=post_ids,
        output_path=output_path,
        chunk_size=chunk_size,
    )
