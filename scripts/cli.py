"""
Command line interface for the Reddit Research Scraper.
"""
import sys
import time
import click

from scripts.models import PostField, CommentField
from scripts.filters import Filters
from scripts.sources import ArcticShiftSource, get_source
from scripts.scraper import RedditScraper


@click.group()
def cli():
    """Reddit Research Scraper: High-performance historical Reddit data extractor."""
    pass


@cli.command()
@click.option("--subreddits", "-s", multiple=True, default=["resumes"], help="Subreddit(s) to scan.")
@click.option("--from", "from_dt", required=True, help="Start date/datetime (YYYY-MM-DD or ISO).")
@click.option("--to", "to_dt", default=None, help="End date/datetime (YYYY-MM-DD or ISO, defaults to today).")
@click.option("--shard-days", default=180, type=int, help="Shard window size in days.")
@click.option("--include-fields", "-i", multiple=True, help="Important post fields to keep (validated against PostField enum).")
@click.option("--exclude-fields", "-e", multiple=True, help="Unimportant post fields to drop (validated against PostField enum).")
@click.option("--comment-include-fields", multiple=True, help="Important comment fields to keep.")
@click.option("--comment-exclude-fields", multiple=True, help="Unimportant comment fields to drop.")
@click.option("--posts-out", default="data/curated_posts.parquet", help="Parquet output destination for posts.")
@click.option("--comments-out", default="data/curated_comments.parquet", help="Parquet output destination for comments.")
@click.option("--post-workers", default=4, type=int, help="Parallel shard post workers.")
@click.option("--comment-workers", default=5, type=int, help="Async comment concurrency workers.")
@click.option("--source", default="arctic_shift", type=click.Choice(["arctic_shift"]), help="Data source provider.")
def run(
    subreddits, from_dt, to_dt, shard_days,
    include_fields, exclude_fields, comment_include_fields, comment_exclude_fields,
    posts_out, comments_out, post_workers, comment_workers, source
):
    """Run full pipeline: scrape posts, filter cohort, and extract comment trees."""
    target_subs = list(subreddits)

    try:
        filters = Filters(
            post_filter=None,
            comment_filter=None,
            post_include_fields=list(include_fields) if include_fields else None,
            post_exclude_fields=list(exclude_fields) if exclude_fields else None,
            comment_include_fields=list(comment_include_fields) if comment_include_fields else None,
            comment_exclude_fields=list(comment_exclude_fields) if comment_exclude_fields else None,
            validate=True,
        )
    except ValueError as e:
        click.secho(f"\n[!] Field Validation Error: {e}", fg="red", err=True)
        sys.exit(1)

    scraper = RedditScraper(
        filters=filters,
        source=get_source(source),
        post_workers=post_workers,
        comment_workers=comment_workers,
        shard_days=shard_days,
    )

    start_time = time.time()
    click.echo(f"Reddit Research Scraper: {len(target_subs)} subreddits (shard_days={shard_days})")
    click.echo(f"Window: from {from_dt} to {to_dt or 'now'}")
    if filters.post_include_fields:
        click.echo(f"Post Fields Kept: {sorted(list(filters.post_include_fields))}")
    if filters.post_exclude_fields:
        click.echo(f"Post Fields Dropped: {sorted(list(filters.post_exclude_fields))}")

    posts, comments = scraper.run(
        subreddits=target_subs,
        from_dt=from_dt,
        to_dt=to_dt,
        posts_output=posts_out,
        comments_output=comments_out,
    )

    elapsed = round(time.time() - start_time, 1)
    click.echo(f"[✓] Pipeline complete in {elapsed}s")
    click.echo(f"    Posts:    {len(posts):,} -> {posts_out}")
    click.echo(f"    Comments: {comments:,} -> {comments_out}")


@cli.command()
@click.option("--subreddits", "-s", multiple=True, default=["resumes"], help="Subreddit(s) to scan.")
@click.option("--from", "from_dt", required=True, help="Start date/datetime (YYYY-MM-DD or ISO).")
@click.option("--to", "to_dt", default=None, help="End date/datetime (YYYY-MM-DD or ISO, defaults to today).")
@click.option("--shard-days", default=180, type=int, help="Shard window size in days.")
@click.option("--include-fields", "-i", multiple=True, help="Important post fields to keep.")
@click.option("--exclude-fields", "-e", multiple=True, help="Unimportant post fields to drop.")
@click.option("--output", "-o", default="data/curated_posts.parquet", help="Parquet output destination.")
@click.option("--post-workers", default=4, type=int, help="Parallel shard post workers.")
@click.option("--source", default="arctic_shift", type=click.Choice(["arctic_shift"]), help="Data source provider.")
def posts(subreddits, from_dt, to_dt, shard_days, include_fields, exclude_fields, output, post_workers, source):
    """Scrape and filter Reddit posts between --from and --to dates."""
    target_subs = list(subreddits)
    filters = Filters(
        post_filter=None,
        post_include_fields=list(include_fields) if include_fields else None,
        post_exclude_fields=list(exclude_fields) if exclude_fields else None,
    )
    scraper = RedditScraper(
        filters=filters,
        source=get_source(source),
        post_workers=post_workers,
        shard_days=shard_days,
    )
    scraper.scrape_posts(
        subreddits=target_subs,
        from_dt=from_dt,
        to_dt=to_dt,
        output_path=output,
    )


@cli.command()
@click.option("--post-id", "-p", "post_ids", multiple=True, required=True, help="Post ID(s) to fetch comments for.")
@click.option("--include-fields", "-i", multiple=True, help="Important comment fields to keep.")
@click.option("--exclude-fields", "-e", multiple=True, help="Unimportant comment fields to drop.")
@click.option("--output", "-o", default="data/curated_comments.parquet", help="Parquet output destination.")
@click.option("--workers", "-w", default=5, type=int, help="Async concurrency limit.")
@click.option("--source", default="arctic_shift", type=click.Choice(["arctic_shift"]), help="Data source provider.")
def comments(post_ids, include_fields, exclude_fields, output, workers, source):
    """Scrape comment trees for given post IDs."""
    filters = Filters(
        comment_filter=None,
        comment_include_fields=list(include_fields) if include_fields else None,
        comment_exclude_fields=list(exclude_fields) if exclude_fields else None,
    )
    scraper = RedditScraper(
        filters=filters,
        source=get_source(source),
        comment_workers=workers,
    )
    scraper.scrape_comments(post_ids=list(post_ids), output_path=output)


@cli.command()
def fields():
    """List all valid PostField and CommentField enumerations with descriptions."""
    click.echo(f"\nVALID POST FIELDS ({len(PostField)}):")
    for p in sorted(list(PostField), key=lambda x: x.value):
        desc = f" — {p.description}" if p.description else ""
        click.echo(f"  • {p.value:<30}{desc}")
    click.echo(f"\nVALID COMMENT FIELDS ({len(CommentField)}):")
    for c in sorted(list(CommentField), key=lambda x: x.value):
        desc = f" — {c.description}" if c.description else ""
        click.echo(f"  • {c.value:<30}{desc}")


if __name__ == "__main__":
    cli()
