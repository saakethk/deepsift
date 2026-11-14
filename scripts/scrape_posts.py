"""
Backwards-compatible interface for post scraping.
Delegates to the generalized RedditScraper class.
"""
from typing import Union, List, Optional
from datetime import datetime
from scripts.filters import Filters
from scripts.scraper import RedditScraper


def collect_cohort_posts(
    subreddit: Union[str, List[str]] = "resumes",
    days_back: int = 5 * 365,
    shard_days: int = 180,
    max_workers: int = 4,
    output_path: str = "data/curated_posts_5yr.parquet",
    anchor_dt: Optional[datetime] = None,
    filters: Optional[Filters] = None,
) -> list[str]:
    scraper = RedditScraper(
        filters=filters or Filters(),
        post_workers=max_workers,
        shard_days=shard_days,
    )
    return scraper.scrape_posts(
        subreddits=subreddit,
        days_back=days_back,
        output_path=output_path,
        anchor_dt=anchor_dt,
    )
