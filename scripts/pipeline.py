"""
Full 5-Year Reddit Resume Research Pipeline.
Orchestrates:
1. Scanning historical posts in parallel time shards (anchored to midnight UTC)
2. Filtering candidates by score > 0, num_comments > 10, picture URL
3. Concurrently fetching full comment trees with automatic exponential backoff
4. Streaming all data to compact Parquet files
"""
import sys
from pathlib import Path

# Enable importing sibling modules regardless of how the script is invoked
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import time
from datetime import datetime, timezone
from scrape_posts import collect_cohort_posts
from scrape_comments import collect_cohort_comments


def run_pipeline(
    subreddit: str = "resumes",
    days_back: int = 5 * 365,
    posts_output: str = "data/curated_posts_5yr.parquet",
    comments_output: str = "data/curated_comments_5yr.parquet",
    max_post_workers: int = 4,
    comment_concurrency: int = 5,
    anchor_date_str: str = None,
):
    start_time = time.time()

    # Determine fixed anchor datetime
    if anchor_date_str:
        anchor_dt = datetime.strptime(anchor_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        now_utc = datetime.now(timezone.utc)
        anchor_dt = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

    print("=" * 65)
    print(f"Starting Reddit Research Scraper: r/{subreddit} ({days_back} days)")
    print(f"Anchored Date: {anchor_dt.strftime('%Y-%m-%d')} 00:00:00 UTC")
    print("=" * 65)

    # Phase 1: Post scanning with sharding & field projection
    matched_ids = collect_cohort_posts(
        subreddit=subreddit,
        days_back=days_back,
        max_workers=max_post_workers,
        output_path=posts_output,
        anchor_dt=anchor_dt,
    )

    if not matched_ids:
        print("[!] No matching posts found. Exiting.")
        return

    # Phase 2: Async comment tree extraction
    total_comments = collect_cohort_comments(
        post_ids=matched_ids,
        output_path=comments_output,
        concurrency_limit=comment_concurrency,
    )

    elapsed = round(time.time() - start_time, 1)
    print("=" * 65)
    print(f" Pipeline Finished in {elapsed}s")
    print(f" Cohort Posts Saved:    {len(matched_ids):,} -> {posts_output}")
    print(f" Comments Saved:        {total_comments:,} -> {comments_output}")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape 5-year curated Reddit resume cohort.")
    parser.add_argument("--subreddit", type=str, default="resumes", help="Target subreddit")
    parser.add_argument("--days", type=int, default=5 * 365, help="Days back to scrape")
    parser.add_argument("--anchor", type=str, default=None, help="Fixed anchor date YYYY-MM-DD (defaults to today's midnight UTC)")
    parser.add_argument("--posts_out", type=str, default="data/curated_posts_5yr.parquet", help="Output path for posts")
    parser.add_argument("--comments_out", type=str, default="data/curated_comments_5yr.parquet", help="Output path for comments")
    parser.add_argument("--post_workers", type=int, default=4, help="Parallel post shard workers")
    parser.add_argument("--comment_workers", type=int, default=5, help="Async comment workers")

    args = parser.parse_args()
    run_pipeline(
        subreddit=args.subreddit,
        days_back=args.days,
        posts_output=args.posts_out,
        comments_output=args.comments_out,
        max_post_workers=args.post_workers,
        comment_concurrency=args.comment_workers,
        anchor_date_str=args.anchor,
    )
