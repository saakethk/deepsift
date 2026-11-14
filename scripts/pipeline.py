"""
Reddit Research Pipeline CLI.
Runs multi-subreddit extraction using the generalized RedditScraper and Filters library.
Requires explicit --from and optional --to date window.
"""
import sys
import argparse
import time
import pandas as pd

from scripts.enums import PostField, CommentField
from scripts.models import Post, Comment
from scripts.filters import Filters, resume_cohort_post_filter, default_comment_filter
from scripts.sources import Source, ArcticShiftSource
from scripts.scraper import RedditScraper


def load_subreddits_from_file(csv_path: str) -> list[str]:
    """Extracts subreddit names from a CSV file."""
    df = pd.read_csv(csv_path)
    for col in ["subreddit_name", "subreddit", "name"]:
        if col in df.columns:
            return df[col].dropna().astype(str).tolist()
    return df.iloc[:, 0].dropna().astype(str).tolist()


def run_pipeline():
    parser = argparse.ArgumentParser(
        description="Scrape curated Reddit research cohort with custom filters and field selection."
    )
    # Help / Inspection
    parser.add_argument(
        "--list_fields", action="store_true", help="Print all valid PostField and CommentField enumerations and exit."
    )

    # Subreddits and time range
    parser.add_argument("--source", type=str, default="arctic_shift", choices=["arctic_shift"], help="Data source provider (default: arctic_shift)")
    parser.add_argument("--subreddits", nargs="+", default=["resumes"], help="Target subreddits")
    parser.add_argument("--subreddits_file", type=str, default=None, help="Path to CSV containing subreddit names")
    parser.add_argument("--from", "--from_date", "--from_dt", dest="from_dt", type=str, required=False, default=None,
                        help="Start date/datetime (YYYY-MM-DD or ISO). Required unless --list_fields is passed.")
    parser.add_argument("--to", "--to_date", "--to_dt", dest="to_dt", type=str, default=None,
                        help="End date/datetime (YYYY-MM-DD or ISO, defaults to today)")
    parser.add_argument("--shard_days", type=int, default=180, help="Size of each time shard in days (default: 180)")

    # Column / Field Selection (Enumerations)
    parser.add_argument(
        "--include_fields", "--post_include_fields", nargs="+", default=None, dest="post_include_fields",
        help="Important post fields to keep (validated against PostField enum, defaults to all raw fields)."
    )
    parser.add_argument(
        "--exclude_fields", "--post_exclude_fields", nargs="+", default=None, dest="post_exclude_fields",
        help="Unimportant post fields to drop (validated against PostField enum)."
    )
    parser.add_argument(
        "--comment_include_fields", nargs="+", default=None,
        help="Important comment fields to keep (validated against CommentField enum, defaults to all raw fields)."
    )
    parser.add_argument(
        "--comment_exclude_fields", nargs="+", default=None,
        help="Unimportant comment fields to drop (validated against CommentField enum)."
    )

    # Output and performance arguments
    parser.add_argument("--posts_out", type=str, default="data/curated_posts.parquet", help="Output path for posts")
    parser.add_argument("--comments_out", type=str, default="data/curated_comments.parquet", help="Output path for comments")
    parser.add_argument("--post_workers", type=int, default=4, help="Post shard workers")
    parser.add_argument("--comment_workers", type=int, default=5, help="Async comment workers")

    args = parser.parse_args()

    if args.list_fields:
        print("\n" + "=" * 60)
        print(f"VALID POST FIELDS ({len(PostField)}):")
        print("=" * 60)
        for f in sorted([p.value for p in PostField]):
            print(f"  - {f}")
        print("\n" + "=" * 60)
        print(f"VALID COMMENT FIELDS ({len(CommentField)}):")
        print("=" * 60)
        for f in sorted([c.value for c in CommentField]):
            print(f"  - {f}")
        print("=" * 60)
        return

    if not args.from_dt:
        print("\n[!] Error: --from (start date/datetime) is required. Example: --from 2021-01-01", file=sys.stderr)
        sys.exit(1)

    # Determine subreddits list
    if args.subreddits_file:
        subreddits = load_subreddits_from_file(args.subreddits_file)
        print(f"[*] Loaded {len(subreddits)} subreddits from {args.subreddits_file}")
    else:
        subreddits = args.subreddits

    # Initialize Filters with default cohort filters and column selection
    try:
        filters = Filters(
            post_filter=resume_cohort_post_filter,
            comment_filter=default_comment_filter,
            post_include_fields=args.post_include_fields,
            comment_include_fields=args.comment_include_fields,
            post_exclude_fields=args.post_exclude_fields,
            comment_exclude_fields=args.comment_exclude_fields,
            validate=True,
        )
    except ValueError as e:
        print(f"\n[!] Field Validation Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.source == "arctic_shift":
        source = ArcticShiftSource()
    else:
        source = ArcticShiftSource()

    scraper = RedditScraper(
        filters=filters,
        source=source,
        post_workers=args.post_workers,
        comment_workers=args.comment_workers,
        shard_days=args.shard_days,
    )

    start_time = time.time()
    print("=" * 65)
    print(f"Reddit Research Scraper: {len(subreddits)} subreddits (shard_days={args.shard_days})")
    print(f"Window: from {args.from_dt} to {args.to_dt or 'now'}")
    if filters.post_include_fields:
        print(f"Post Fields Kept: {sorted(list(filters.post_include_fields))}")
    if filters.post_exclude_fields:
        print(f"Post Fields Dropped: {sorted(list(filters.post_exclude_fields))}")
    print("=" * 65)

    posts, comments = scraper.run(
        subreddits=subreddits,
        from_dt=args.from_dt,
        to_dt=args.to_dt,
        posts_output=args.posts_out,
        comments_output=args.comments_out,
    )

    elapsed = round(time.time() - start_time, 1)
    print("=" * 65)
    print(f" Pipeline Finished in {elapsed}s")
    print(f" Posts Saved:    {len(posts):,} -> {args.posts_out}")
    print(f" Comments Saved: {comments:,} -> {args.comments_out}")
    print("=" * 65)


if __name__ == "__main__":
    run_pipeline()
