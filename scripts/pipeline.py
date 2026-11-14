"""
Full Reddit Resume Research Pipeline CLI.
Runs multi-subreddit extraction using the generalized RedditScraper and Filters library.
"""
import os
import argparse
import time
import pandas as pd
from datetime import datetime, timezone

from scripts.models import Post, Comment
from scripts.filters import Filters, resume_cohort_post_filter, default_comment_filter
from scripts.scraper import RedditScraper


def load_subreddits_from_file(csv_path: str) -> list[str]:
    """Extracts subreddit names from a CSV file."""
    df = pd.read_csv(csv_path)
    for col in ["subreddit_name", "subreddit", "name"]:
        if col in df.columns:
            return df[col].dropna().astype(str).tolist()
    return df.iloc[:, 0].dropna().astype(str).tolist()


def run_pipeline():
    parser = argparse.ArgumentParser(description="Scrape curated Reddit research cohort.")
    parser.add_argument("--subreddits", nargs="+", default=["resumes"], help="Target subreddits")
    parser.add_argument("--subreddits_file", type=str, default=None, help="Path to CSV containing subreddit names")
    parser.add_argument("--days", type=int, default=5 * 365, help="Days back to scrape")
    parser.add_argument("--shard_days", type=int, default=180, help="Size of each time shard in days (default: 180)")
    parser.add_argument("--anchor", type=str, default=None, help="Anchor date YYYY-MM-DD")
    
    # Optional threshold adjustments for default cohort filter
    parser.add_argument("--min_score", type=int, default=1, help="Minimum post score threshold (default: 1)")
    parser.add_argument("--min_comments", type=int, default=11, help="Minimum post comments threshold (default: 11)")
    parser.add_argument("--no_image_filter", action="store_true", help="Disable mandatory image URL check")
    parser.add_argument("--include_automod", action="store_true", help="Include AutoModerator comments")
    
    # Output and performance arguments
    parser.add_argument("--posts_out", type=str, default="data/curated_posts_5yr.parquet", help="Output path for posts")
    parser.add_argument("--comments_out", type=str, default="data/curated_comments_5yr.parquet", help="Output path for comments")
    parser.add_argument("--post_workers", type=int, default=4, help="Post shard workers")
    parser.add_argument("--comment_workers", type=int, default=5, help="Async comment workers")

    args = parser.parse_args()

    # Determine subreddits list
    if args.subreddits_file:
        subreddits = load_subreddits_from_file(args.subreddits_file)
        print(f"[*] Loaded {len(subreddits)} subreddits from {args.subreddits_file}")
    else:
        subreddits = args.subreddits

    # Build custom filter function from CLI arguments
    def cli_post_filter(post: Post) -> bool:
        if post.score < args.min_score:
            return False
        if post.num_comments < args.min_comments:
            return False
        if not args.no_image_filter and not post.is_image:
            return False
        return True

    def cli_comment_filter(comment: Comment) -> bool:
        if not args.include_automod and comment.is_automod:
            return False
        return bool(comment.body.strip())

    filters = Filters(
        post_filter=cli_post_filter,
        comment_filter=cli_comment_filter,
    )

    # Determine fixed anchor datetime
    if args.anchor:
        anchor_dt = datetime.strptime(args.anchor, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        now_utc = datetime.now(timezone.utc)
        anchor_dt = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

    scraper = RedditScraper(
        filters=filters,
        post_workers=args.post_workers,
        comment_workers=args.comment_workers,
        shard_days=args.shard_days,
    )

    start_time = time.time()
    print("=" * 65)
    print(f"Reddit Research Scraper: {len(subreddits)} subreddits ({args.days} days, shard_days={args.shard_days})")
    print(f"Anchored Date: {anchor_dt.strftime('%Y-%m-%d')} 00:00:00 UTC")
    print(f"Criteria: score >= {args.min_score}, comments >= {args.min_comments}, require_image={not args.no_image_filter}")
    print("=" * 65)

    posts, comments = scraper.run(
        subreddits=subreddits,
        days_back=args.days,
        posts_output=args.posts_out,
        comments_output=args.comments_out,
        anchor_dt=anchor_dt,
    )

    elapsed = round(time.time() - start_time, 1)
    print("=" * 65)
    print(f" Pipeline Finished in {elapsed}s")
    print(f" Posts Saved:    {len(posts):,} -> {args.posts_out}")
    print(f" Comments Saved: {comments:,} -> {args.comments_out}")
    print("=" * 65)


if __name__ == "__main__":
    run_pipeline()
