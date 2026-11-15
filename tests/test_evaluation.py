"""
Unit tests for the evaluation and benchmarking package.
Verifies metrics generation, data parity checks, and report formatting.
"""
from evaluation.__main__ import run_benchmark, format_markdown_report


def test_evaluation_run_benchmark_dummy():
    metrics = run_benchmark(
        mode="dummy",
        dummy_posts=20,
        dummy_comments_per_post=2,
        dummy_seed=42,
        post_workers=2,
        comment_workers=2,
    )

    assert "deepsift" in metrics
    assert "sequential" in metrics
    assert "comparison" in metrics

    ds = metrics["deepsift"]
    sq = metrics["sequential"]
    comp = metrics["comparison"]

    assert ds["posts_count"] == 20
    assert sq["posts_count"] == 20
    assert comp["posts_count_match"] is True

    assert ds["comments_count"] == 40
    assert sq["comments_count"] == 40
    assert comp["comments_count_match"] is True

    assert ds["elapsed_seconds"] > 0
    assert sq["elapsed_seconds"] > 0
    assert comp["speedup_factor"] > 0

    report = format_markdown_report(metrics)
    assert "# DeepSift vs Sequential Execution Evaluation" in report
    assert "| **Total Elapsed Time** |" in report
    assert "| **Posts Scraped** |" in report
