"""
Click-based CLI interface for the Reddit Research Scraper.
"""
import click
from scripts.enums import PostField, CommentField
from scripts.filters import Filters, resume_cohort_post_filter, default_comment_filter
from scripts.sources import ArcticShiftSource
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
@click.option("--output", "-o", default="data/curated_posts.parquet", help="Parquet output destination.")
def posts(subreddits, from_dt, to_dt, shard_days, include_fields, exclude_fields, output):
    """Scrape and filter Reddit posts between --from and --to dates."""
    filters = Filters(
        post_filter=resume_cohort_post_filter,
        post_include_fields=list(include_fields) if include_fields else None,
        post_exclude_fields=list(exclude_fields) if exclude_fields else None,
    )
    scraper = RedditScraper(filters=filters, shard_days=shard_days)
    matched = scraper.scrape_posts(
        subreddits=list(subreddits),
        from_dt=from_dt,
        to_dt=to_dt,
        output_path=output,
    )
    click.echo(click.style(f"[✓] Scrape complete. Saved {len(matched):,} posts to {output}", fg="green"))


@cli.command()
@click.option("--post-id", "-p", "post_ids", multiple=True, required=True, help="Post ID(s) to fetch comments for.")
@click.option("--output", "-o", default="data/curated_comments.parquet", help="Parquet output destination.")
@click.option("--workers", "-w", default=5, type=int, help="Async concurrency limit.")
def comments(post_ids, output, workers):
    """Scrape comment trees for given post IDs."""
    scraper = RedditScraper(comment_workers=workers)
    count = scraper.scrape_comments(post_ids=list(post_ids), output_path=output)
    click.echo(click.style(f"[✓] Comments complete. Saved {count:,} comments to {output}", fg="green"))


@cli.command()
def fields():
    """List all valid PostField and CommentField enumerations."""
    click.echo(f"\nVALID POST FIELDS ({len(PostField)}):")
    for f in sorted([p.value for p in PostField]):
        click.echo(f"  • {f}")
    click.echo(f"\nVALID COMMENT FIELDS ({len(CommentField)}):")
    for f in sorted([c.value for c in CommentField]):
        click.echo(f"  • {f}")


if __name__ == "__main__":
    cli()
