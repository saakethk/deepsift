"""
Performance evaluation and benchmarking module.
Compares DeepSift against naive sequential scraping across execution time,
peak memory, throughput, and detailed API request latency profiles.
"""
import os
import time
import argparse
import tempfile
import tracemalloc
from typing import Dict, Any

from deepsift.scraper import RedditScraper
from deepsift.filters import Filters
from deepsift.sources.dummy import DummySource
from deepsift.sources.arctic_shift import ArcticShiftSource
from deepsift.models import PostField, CommentField
from evaluation.baseline import SequentialScraper
from evaluation.utils import track_api_calls


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
    Returns metrics dictionary with timing, peak memory, throughput, and API latency.
    """
    projected_post_fields = [
        PostField.ID, PostField.TITLE, PostField.SCORE,
        PostField.NUM_COMMENTS, PostField.CREATED_UTC, PostField.SUBREDDIT,
    ]
    projected_comment_fields = [
        CommentField.ID, CommentField.POST_ID, CommentField.PARENT_ID,
        CommentField.BODY, CommentField.SCORE,
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        posts_out = os.path.join(tmpdir, "deepsift_posts.parquet")
        comments_out = os.path.join(tmpdir, "deepsift_comments.parquet")

        filters = Filters(
            post_filter=lambda p: p.score is not None and p.score >= 0,
            comment_filter=lambda c: len(c.body) > 0,
            post_include_fields=projected_post_fields,
            comment_include_fields=projected_comment_fields,
        )

        source = (
            DummySource(posts_per_shard=dummy_posts, comments_per_post=dummy_comments_per_post, seed=dummy_seed)
            if mode == "dummy"
            else ArcticShiftSource()
        )
        scraper = RedditScraper(filters=filters, source=source, shard_days=1, post_workers=post_workers, comment_workers=comment_workers)

        tracemalloc.start()
        t0 = time.perf_counter()
        with track_api_calls() as ds_net:
            posts_ids, comments_count = scraper.run(
                subreddits=[subreddit],
                from_dt=after_ts,
                to_dt=before_ts,
                posts_output=posts_out,
                comments_output=comments_out,
            )
        elapsed_ds = time.perf_counter() - t0
        _, peak_ram_ds = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        ds_summary = {
            "elapsed_seconds": round(elapsed_ds, 3),
            "peak_memory_mb": round(peak_ram_ds / (1024 * 1024), 2),
            "posts_count": len(posts_ids),
            "comments_count": comments_count,
            "posts_per_second": round(len(posts_ids) / max(elapsed_ds, 0.001), 1),
            "comments_per_second": round(comments_count / max(elapsed_ds, 0.001), 1),
            "api": ds_net.summary(wall_clock_sec=elapsed_ds),
        }

    sequential = SequentialScraper(
        source_type="dummy" if mode == "dummy" else "arctic_shift",
        dummy_seed=dummy_seed,
        post_filter=lambda p: p.get("score") is not None and p.get("score", 0) >= 0,
        comment_filter=lambda c: len(c.get("body", "")) > 0,
    )

    tracemalloc.start()
    t0_seq = time.perf_counter()
    with track_api_calls() as sq_net:
        seq_posts, seq_comments = sequential.run(
            subreddit=subreddit,
            after_ts=after_ts,
            before_ts=before_ts,
            dummy_posts_per_shard=dummy_posts,
            dummy_comments_per_post=dummy_comments_per_post,
        )
    elapsed_seq = time.perf_counter() - t0_seq
    _, peak_ram_seq = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    sq_summary = {
        "elapsed_seconds": round(elapsed_seq, 3),
        "peak_memory_mb": round(peak_ram_seq / (1024 * 1024), 2),
        "posts_count": len(seq_posts),
        "comments_count": len(seq_comments),
        "posts_per_second": round(len(seq_posts) / max(elapsed_seq, 0.001), 1),
        "comments_per_second": round(len(seq_comments) / max(elapsed_seq, 0.001), 1),
        "api": sq_net.summary(wall_clock_sec=elapsed_seq),
    }

    return {
        "mode": mode,
        "subreddit": subreddit,
        "deepsift": ds_summary,
        "sequential": sq_summary,
        "comparison": {
            "speedup_factor": round(elapsed_seq / max(elapsed_ds, 0.001), 2),
            "memory_ratio": round(peak_ram_seq / max(peak_ram_ds, 0.001), 2),
            "posts_count_match": ds_summary["posts_count"] == sq_summary["posts_count"],
            "comments_count_match": ds_summary["comments_count"] == sq_summary["comments_count"],
        },
    }


def format_markdown_report(metrics: Dict[str, Any]) -> str:
    """Formats benchmark results dictionary into a Markdown comparative table."""
    ds, sq, comp = metrics["deepsift"], metrics["sequential"], metrics["comparison"]
    mode_label = "Synthetic (DummySource)" if metrics["mode"] == "dummy" else f"Live (r/{metrics['subreddit']})"

    lines = [
        f"# DeepSift vs Sequential Execution Evaluation",
        f"**Target Cohort**: {mode_label}",
        "",
        "### Ingestion Performance & Memory",
        "| Metric | DeepSift | Sequential Baseline | Difference / Ratio |",
        "| :--- | :--- | :--- | :--- |",
        f"| **Total Elapsed Time** | {ds['elapsed_seconds']}s | {sq['elapsed_seconds']}s | **{comp['speedup_factor']}x faster** |",
        f"| **Peak RAM Consumption** | {ds['peak_memory_mb']} MB | {sq['peak_memory_mb']} MB | **{comp['memory_ratio']}x less memory** |",
        f"| **Posts Scraped** | {ds['posts_count']} | {sq['posts_count']} | Matches: {'✓' if comp['posts_count_match'] else '✗'} |",
        f"| **Comments Extracted** | {ds['comments_count']} | {sq['comments_count']} | Matches: {'✓' if comp['comments_count_match'] else '✗'} |",
        f"| **Post Processing Rate** | {ds['posts_per_second']} posts/s | {sq['posts_per_second']} posts/s | {round(ds['posts_per_second'] / max(sq['posts_per_second'], 0.1), 1)}x throughput |",
        f"| **Comment Processing Rate** | {ds['comments_per_second']} comments/s | {sq['comments_per_second']} comments/s | {round(ds['comments_per_second'] / max(sq['comments_per_second'], 0.1), 1)}x throughput |",
    ]

    ds_api, sq_api = ds.get("api", {}), sq.get("api", {})
    if ds_api.get("request_count", 0) > 0 or sq_api.get("request_count", 0) > 0:
        lines.extend([
            "",
            "### API & Network Latency Profile",
            "| Network Metric | DeepSift | Sequential Baseline | Difference / Ratio |",
            "| :--- | :--- | :--- | :--- |",
            f"| **API Requests Dispatched** | {ds_api.get('request_count', 0)} | {sq_api.get('request_count', 0)} | - |",
            f"| **Average Latency (ms)** | {ds_api.get('avg_latency_ms', 0)} ms | {sq_api.get('avg_latency_ms', 0)} ms | - |",
            f"| **P50 (Median) Latency** | {ds_api.get('p50_latency_ms', 0)} ms | {sq_api.get('p50_latency_ms', 0)} ms | - |",
            f"| **P95 Latency** | {ds_api.get('p95_latency_ms', 0)} ms | {sq_api.get('p95_latency_ms', 0)} ms | - |",
            f"| **Max Request Latency** | {ds_api.get('max_latency_ms', 0)} ms | {sq_api.get('max_latency_ms', 0)} ms | - |",
            f"| **Network Concurrency Overlap** | **{ds_api.get('concurrency_overlap', 1.0)}x** | {sq_api.get('concurrency_overlap', 1.0)}x | Concurrency gain |",
            f"| **Total Payload Transferred** | {ds_api.get('total_payload_kb', 0)} KB | {sq_api.get('total_payload_kb', 0)} KB | **{round(sq_api.get('total_payload_kb', 1) / max(ds_api.get('total_payload_kb', 1), 0.1), 1)}x less bandwidth** |",
            f"| **Average Payload per Req** | {ds_api.get('avg_payload_kb', 0)} KB | {sq_api.get('avg_payload_kb', 0)} KB | Projected payload |",
        ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Evaluate DeepSift against sequential execution baseline.")
    parser.add_argument("--mode", choices=["all", "dummy", "live", "single"], default="all", help="Target mode: all (live + dummy scaling), dummy, live, or single window check.")
    parser.add_argument("--trials", type=int, default=3, help="Number of trials per window for scaling evaluation.")
    parser.add_argument("--subreddit", default="resumes", help="Target subreddit for live evaluation.")
    parser.add_argument("--from-ts", type=int, default=1704150000, help="Epoch timestamp lower bound for single-window check.")
    parser.add_argument("--to-ts", type=int, default=1704153600, help="Epoch timestamp upper bound for single-window check.")
    parser.add_argument("--dummy-posts", type=int, default=100, help="Number of dummy posts to generate for single-window check.")
    parser.add_argument("--dummy-comments", type=int, default=3, help="Number of comments per dummy post for single-window check.")
    parser.add_argument("--post-workers", type=int, default=4, help="DeepSift shard post workers.")
    parser.add_argument("--comment-workers", type=int, default=5, help="DeepSift comment concurrency workers.")
    parser.add_argument("--markdown", action="store_true", help="Print report in Markdown table format.")

    args = parser.parse_args()

    if args.mode in ("all", "dummy", "live") and not args.markdown and args.from_ts == 1704150000 and args.to_ts == 1704153600:
        from evaluation.scaling_experiment import run_scaling_benchmark
        run_scaling_benchmark(
            mode=args.mode,
            trials=args.trials,
            subreddit=args.subreddit,
        )
        return

    metrics = run_benchmark(
        mode="dummy" if args.mode in ("all", "dummy", "single") else "live",
        subreddit=args.subreddit,
        after_ts=args.from_ts,
        before_ts=args.to_ts,
        dummy_posts=args.dummy_posts,
        dummy_comments_per_post=args.dummy_comments,
        post_workers=args.post_workers,
        comment_workers=args.comment_workers,
    )

    print("\n" + format_markdown_report(metrics) + "\n")


if __name__ == "__main__":
    main()
