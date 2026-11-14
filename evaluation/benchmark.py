"""
Performance evaluation and benchmarking module.
Compares DeepSift (concurrent, streaming Parquet, server-side projection)
against naive sequential scraping across execution time, peak memory, and throughput.
"""
import os
import sys
import time
import argparse
import tempfile
import tracemalloc
from typing import Dict, Any, Optional
import pyarrow.parquet as pq

from deepsift.scraper import RedditScraper
from deepsift.filters import Filters
from deepsift.sources.dummy import DummySource
from deepsift.sources.arctic_shift import ArcticShiftSource
from deepsift.models import PostField, CommentField
from evaluation.baseline import SequentialScraper


def run_benchmark(
    mode: str = "dummy",
    subreddit: str = "resumes",
    after_ts: int = 1704150000,
    before_ts: int = 1704153600,
    dummy_posts: int = 200,
    dummy_comments_per_post: int = 4,
    dummy_seed: int = 42,
    post_workers: int = 4,
    comment_workers: int = 5,
) -> Dict[str, Any]:
    """
    Executes comparative benchmark between DeepSift and SequentialScraper.
    Returns metrics dictionary with timing, peak memory, throughput, and speedup ratios.
    """
    results = {
        "mode": mode,
        "subreddit": subreddit,
        "deepsift": {},
        "sequential": {},
        "comparison": {},
    }

    projected_post_fields = [
        PostField.ID, PostField.TITLE, PostField.SCORE,
        PostField.NUM_COMMENTS, PostField.CREATED_UTC, PostField.SUBREDDIT,
    ]
    projected_comment_fields = [
        CommentField.ID, CommentField.POST_ID, CommentField.PARENT_ID,
        CommentField.BODY, CommentField.SCORE,
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        deepsift_posts_out = os.path.join(tmpdir, "deepsift_posts.parquet")
        deepsift_comments_out = os.path.join(tmpdir, "deepsift_comments.parquet")

        filters = Filters(
            post_filter=lambda p: p.score is not None and p.score >= 0,
            comment_filter=lambda c: len(c.body) > 0,
            post_include_fields=projected_post_fields,
            comment_include_fields=projected_comment_fields,
        )

        if mode == "dummy":
            deepsift_source = DummySource(
                posts_per_shard=dummy_posts,
                comments_per_post=dummy_comments_per_post,
                seed=dummy_seed,
            )
        else:
            deepsift_source = ArcticShiftSource()

        scraper = RedditScraper(
            filters=filters,
            source=deepsift_source,
            shard_days=1,
            post_workers=post_workers,
            comment_workers=comment_workers,
        )

        tracemalloc.start()
        start_time = time.perf_counter()

        posts_ids, comments_count = scraper.run(
            subreddits=[subreddit],
            from_dt=after_ts,
            to_dt=before_ts,
            posts_output=deepsift_posts_out,
            comments_output=deepsift_comments_out,
        )

        elapsed_deepsift = time.perf_counter() - start_time
        current_ram, peak_ram_deepsift = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        results["deepsift"] = {
            "elapsed_seconds": round(elapsed_deepsift, 3),
            "peak_memory_mb": round(peak_ram_deepsift / (1024 * 1024), 2),
            "posts_count": len(posts_ids),
            "comments_count": comments_count,
            "posts_per_second": round(len(posts_ids) / max(elapsed_deepsift, 0.001), 1),
            "comments_per_second": round(comments_count / max(elapsed_deepsift, 0.001), 1),
        }

    sequential_scraper = SequentialScraper(
        source_type="dummy" if mode == "dummy" else "arctic_shift",
        dummy_seed=dummy_seed,
        post_filter=lambda p: p.get("score") is not None and p.get("score", 0) >= 0,
        comment_filter=lambda c: len(c.get("body", "")) > 0,
    )

    tracemalloc.start()
    start_time_seq = time.perf_counter()

    seq_posts, seq_comments = sequential_scraper.run(
        subreddit=subreddit,
        after_ts=after_ts,
        before_ts=before_ts,
        dummy_posts_per_shard=dummy_posts,
        dummy_comments_per_post=dummy_comments_per_post,
    )

    elapsed_seq = time.perf_counter() - start_time_seq
    current_ram_seq, peak_ram_seq = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    results["sequential"] = {
        "elapsed_seconds": round(elapsed_seq, 3),
        "peak_memory_mb": round(peak_ram_seq / (1024 * 1024), 2),
        "posts_count": len(seq_posts),
        "comments_count": len(seq_comments),
        "posts_per_second": round(len(seq_posts) / max(elapsed_seq, 0.001), 1),
        "comments_per_second": round(len(seq_comments) / max(elapsed_seq, 0.001), 1),
    }

    speedup = round(elapsed_seq / max(elapsed_deepsift, 0.001), 2)
    memory_ratio = round(peak_ram_seq / max(peak_ram_deepsift, 0.001), 2)

    results["comparison"] = {
        "speedup_factor": speedup,
        "memory_ratio": memory_ratio,
        "posts_count_match": results["deepsift"]["posts_count"] == results["sequential"]["posts_count"],
        "comments_count_match": results["deepsift"]["comments_count"] == results["sequential"]["comments_count"],
    }

    return results


def format_markdown_report(metrics: Dict[str, Any]) -> str:
    """Formats benchmark results dictionary into a Markdown comparative table."""
    ds = metrics["deepsift"]
    sq = metrics["sequential"]
    comp = metrics["comparison"]

    mode_label = "Synthetic (DummySource)" if metrics["mode"] == "dummy" else f"Live (r/{metrics['subreddit']})"

    report = [
        f"# DeepSift vs Sequential Execution Evaluation",
        f"**Target Cohort**: {mode_label}",
        "",
        "| Metric | DeepSift | Sequential Baseline | Difference / Ratio |",
        "| :--- | :--- | :--- | :--- |",
        f"| **Total Elapsed Time** | {ds['elapsed_seconds']}s | {sq['elapsed_seconds']}s | **{comp['speedup_factor']}x faster** |",
        f"| **Peak RAM Consumption** | {ds['peak_memory_mb']} MB | {sq['peak_memory_mb']} MB | **{comp['memory_ratio']}x less memory** |",
        f"| **Posts Scraped** | {ds['posts_count']} | {sq['posts_count']} | Matches: {'✓' if comp['posts_count_match'] else '✗'} |",
        f"| **Comments Extracted** | {ds['comments_count']} | {sq['comments_count']} | Matches: {'✓' if comp['comments_count_match'] else '✗'} |",
        f"| **Post Processing Rate** | {ds['posts_per_second']} posts/s | {sq['posts_per_second']} posts/s | {round(ds['posts_per_second'] / max(sq['posts_per_second'], 0.1), 1)}x throughput |",
        f"| **Comment Processing Rate** | {ds['comments_per_second']} comments/s | {sq['comments_per_second']} comments/s | {round(ds['comments_per_second'] / max(sq['comments_per_second'], 0.1), 1)}x throughput |",
        "",
        "### Architectural Highlights",
        "- **Field Projection**: DeepSift transmits only requested fields over the wire, saving serialization overhead.",
        "- **Async Concurrency**: Comment trees are resolved concurrently using connection pooling rather than blocking HTTP calls.",
        "- **Disk Streaming**: PyArrow batches are streamed directly to snappy-compressed Parquet chunks rather than accumulated in memory.",
    ]
    return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description="Evaluate DeepSift against sequential execution baseline.")
    parser.add_argument("--mode", choices=["dummy", "live"], default="dummy", help="Target source: dummy or live Arctic Shift.")
    parser.add_argument("--subreddit", default="resumes", help="Target subreddit for live evaluation.")
    parser.add_argument("--from-ts", type=int, default=1704150000, help="Epoch timestamp lower bound.")
    parser.add_argument("--to-ts", type=int, default=1704153600, help="Epoch timestamp upper bound.")
    parser.add_argument("--dummy-posts", type=int, default=100, help="Number of dummy posts to generate.")
    parser.add_argument("--dummy-comments", type=int, default=3, help="Number of comments per dummy post.")
    parser.add_argument("--post-workers", type=int, default=4, help="DeepSift shard post workers.")
    parser.add_argument("--comment-workers", type=int, default=5, help="DeepSift comment concurrency workers.")

    args = parser.parse_args()

    print(f"[*] Starting benchmark evaluation in [{args.mode.upper()}] mode...")
    metrics = run_benchmark(
        mode=args.mode,
        subreddit=args.subreddit,
        after_ts=args.from_ts,
        before_ts=args.to_ts,
        dummy_posts=args.dummy_posts,
        dummy_comments_per_post=args.dummy_comments,
        post_workers=args.post_workers,
        comment_workers=args.comment_workers,
    )

    report = format_markdown_report(metrics)
    print("\n" + report + "\n")


if __name__ == "__main__":
    main()
