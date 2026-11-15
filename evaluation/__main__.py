"""
Unified DeepSift benchmarking and performance evaluation suite.
Evaluates multi-worker post sharding scaling (1, 2, 4, 6 workers) across
multi-day query windows (1 to 10 days) using native RedditScraper execution.
"""
import os
import sys
import time
import argparse
import tempfile
import tracemalloc
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib_cache"
import matplotlib.pyplot as plt

from deepsift.scraper import RedditScraper
from deepsift.filters import Filters
from deepsift.sources.dummy import DummySource
from deepsift.sources.arctic_shift import ArcticShiftSource
from deepsift.models import PostField, CommentField
from evaluation.utils import get_git_commit, get_run_timestamp, save_benchmark_artifacts, track_api_calls


DEFAULT_WINDOWS = [
    ("1 Day (~100)", 1704067200, 1704153600),
    ("3 Days (~300)", 1703894400, 1704153600),
    ("5 Days (~500)", 1703721600, 1704153600),
    ("7 Days (~700)", 1703548800, 1704153600),
    ("10 Days (~1000)", 1703289600, 1704153600),
]
WORKER_LEVELS = [1, 2, 4, 6]
WORKER_COLORS = {
    1: ("#ef4444", "#b91c1c", "#7f1d1d", "1 Worker (Sequential)"),
    2: ("#38bdf8", "#0284c7", "#0284c7", "2 Shard Workers"),
    4: ("#10b981", "#047857", "#047857", "4 Shard Workers"),
    6: ("#6366f1", "#4338ca", "#4338ca", "6 Shard Workers"),
}


def render_scaling_chart(
    df: pd.DataFrame,
    title_prefix: str,
    commit_hash: str = "latest",
    extra_note: str = "",
) -> plt.Figure:
    """Renders grouped bar comparison across 1, 2, 4, 6 shard workers with SEM error bars."""
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig, ax = plt.subplots(figsize=(12.5, 6.2), facecolor="#ffffff")

    windows = df["window"].tolist()
    posts = df["posts"].tolist()
    labels = [f"{w.split(' ')[0]} {w.split(' ')[1]}\n({p} posts)" for w, p in zip(windows, posts)]
    x = np.arange(len(labels))
    width = 0.19

    trials_count = int(df["trials"].iloc[0]) if "trials" in df.columns else 1
    trials_note = f" • {trials_count} Trials (Mean ± SEM)" if trials_count > 1 else ""

    offsets = [-1.5 * width, -0.5 * width, 0.5 * width, 1.5 * width]
    max_val = 0.0

    for idx, w in enumerate(WORKER_LEVELS):
        color, border, err_color, label = WORKER_COLORS[w]
        time_col = f"time_{w}w_sec"
        sem_col = f"time_{w}w_sem"

        heights = df[time_col]
        yerr = df.get(sem_col)

        rects = ax.bar(
            x + offsets[idx],
            heights,
            width,
            yerr=yerr,
            capsize=3,
            error_kw=dict(ecolor=err_color, lw=1.2, capthick=1.2),
            label=f"DeepSift ({label})",
            color=color,
            edgecolor=border,
            alpha=0.9,
        )

        for rect_idx, rect in enumerate(rects):
            h = rect.get_height()
            err = float(yerr.iloc[rect_idx]) if yerr is not None else 0.0
            top = h + err
            max_val = max(max_val, top)
            if h >= 0.01:
                label_txt = f"{h:.2f}s" if err <= 0.02 else f"{h:.2f}±{err:.2f}s"
                ax.text(
                    rect.get_x() + rect.get_width() / 2,
                    top + 0.04,
                    label_txt,
                    ha="center",
                    va="bottom",
                    fontsize=7,
                    fontweight="bold",
                    color=err_color,
                )

    full_title = (
        f"{title_prefix}: Post Ingestion Scaling Across Worker Levels (1, 2, 4, 6 Workers)\n"
        f"Wall-Clock Execution Time Across Multi-Day Query Windows{trials_note}{extra_note} • Commit: {commit_hash}"
    )
    ax.set_title(full_title, fontsize=12, fontweight="bold", pad=14, color="#0f172a")
    ax.set_ylabel("Execution Time (Seconds)", fontsize=10.5, fontweight="semibold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9.5)
    ax.grid(True, linestyle="--", alpha=0.5, axis="y")
    ax.set_ylim(0, max_val * 1.25)
    ax.legend(loc="upper left", frameon=True, facecolor="#ffffff", framealpha=0.9, fontsize=9)
    fig.tight_layout()
    return fig


def run_synthetic_scaling(
    windows: Optional[List[Tuple[str, int, int]]] = None,
    dummy_seed: int = 42,
    simulated_latency: float = 0.25,
    trials: int = 3,
    results_dir: str = "evaluation/results",
    file_tag: Optional[str] = None,
    window_post_counts: Optional[Dict[str, int]] = None,
) -> pd.DataFrame:
    """Executes synthetic scaling benchmark across 1, 2, 4, 6 worker levels with simulated API latency."""
    if windows is None:
        windows = DEFAULT_WINDOWS

    commit_hash = get_git_commit()
    curr_iso, default_tag = get_run_timestamp()
    iso_timestamp = curr_iso
    if file_tag is None:
        file_tag = default_tag

    print(f"\n[*] Running Synthetic Scaling Benchmark ({trials} trials, {simulated_latency*1000:.0f}ms simulated latency, Commit: {commit_hash})...")
    if window_post_counts:
        print(f"    Matching post counts from live benchmark: {window_post_counts}")

    records = []
    trial_records = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for label, after_ts, before_ts in windows:
            target_posts = window_post_counts.get(label) if window_post_counts else None
            shard_post_counts = None
            if target_posts is not None:
                dummy_scraper = RedditScraper(shard_days=1)
                shards, _, _ = dummy_scraper._generate_shards(after_ts, before_ts)
                n_shards = max(1, len(shards))
                base = target_posts // n_shards
                rem = target_posts % n_shards
                shard_post_counts = {shard: base + (1 if idx < rem else 0) for idx, shard in enumerate(shards)}

            print(f"    Evaluating synthetic window: {label} (target posts: {target_posts if target_posts is not None else '~default'})...")

            trial_times = {w: [] for w in WORKER_LEVELS}
            trial_rams = {w: [] for w in WORKER_LEVELS}
            posts_count = 0

            for trial in range(1, trials + 1):
                t_run = {
                    "trial": trial,
                    "timestamp": iso_timestamp,
                    "git_commit": commit_hash,
                    "window": label,
                }

                for w in WORKER_LEVELS:
                    ds_out = os.path.join(tmpdir, f"ds_{before_ts}_{w}w_t{trial}.parquet")
                    scraper = RedditScraper(
                        filters=Filters(),
                        source=DummySource(
                            posts_per_shard=shard_post_counts if shard_post_counts is not None else 100,
                            batch_size=100,
                            seed=dummy_seed + trial,
                            simulated_latency=simulated_latency,
                        ),
                        shard_days=1,
                        post_workers=w,
                    )
                    tracemalloc.start()
                    t0 = time.perf_counter()
                    posts = scraper.scrape_posts(
                        subreddits=["resumes"],
                        from_dt=after_ts,
                        to_dt=before_ts,
                        output_path=ds_out,
                    )
                    elapsed = time.perf_counter() - t0
                    _, peak_ram = tracemalloc.get_traced_memory()
                    tracemalloc.stop()

                    posts_count = len(posts)
                    trial_times[w].append(elapsed)
                    trial_rams[w].append(peak_ram / (1024 * 1024))
                    t_run[f"time_{w}w_sec"] = round(elapsed, 4)
                    t_run[f"ram_{w}w_mb"] = round(peak_ram / (1024 * 1024), 2)

                t_run["posts"] = posts_count
                trial_records.append(t_run)

            summary_row = {
                "timestamp": iso_timestamp,
                "git_commit": commit_hash,
                "window": label,
                "trials": trials,
                "posts": posts_count,
            }

            for w in WORKER_LEVELS:
                mean_t = float(np.mean(trial_times[w]))
                sem_t = float(np.std(trial_times[w], ddof=1) / np.sqrt(trials)) if trials > 1 else 0.0
                mean_ram = float(np.mean(trial_rams[w]))
                summary_row[f"time_{w}w_sec"] = round(mean_t, 3)
                summary_row[f"time_{w}w_sem"] = round(sem_t, 3)
                summary_row[f"ram_{w}w_mb"] = round(mean_ram, 2)

            t1 = summary_row["time_1w_sec"]
            summary_row["speedup_2w"] = round(t1 / max(summary_row["time_2w_sec"], 0.001), 2)
            summary_row["speedup_4w"] = round(t1 / max(summary_row["time_4w_sec"], 0.001), 2)
            summary_row["speedup_6w"] = round(t1 / max(summary_row["time_6w_sec"], 0.001), 2)
            records.append(summary_row)

            print(
                f"      -> {label} ({posts_count} posts): "
                f"1w={summary_row['time_1w_sec']:.2f}s | 2w={summary_row['time_2w_sec']:.2f}s | "
                f"4w={summary_row['time_4w_sec']:.2f}s | 6w={summary_row['time_6w_sec']:.2f}s"
            )

    df = pd.DataFrame(records)
    trials_df = pd.DataFrame(trial_records)
    fig = render_scaling_chart(
        df,
        title_prefix="Synthetic Benchmark (DummySource)",
        commit_hash=commit_hash,
        extra_note=f" • {simulated_latency*1000:.0f}ms Simulated Latency",
    )

    csv_path, png_path = save_benchmark_artifacts(
        df=df,
        fig=fig,
        name_prefix="synthetic_scaling",
        results_dir=results_dir,
        file_tag=file_tag,
        trials_df=trials_df,
    )
    plt.close()

    print(f"\n[✓] Saved synthetic scaling summary table to: {csv_path}")
    print(f"[✓] Saved synthetic scaling figure to:        {png_path}")
    return df


def run_live_scaling(
    subreddit: str = "resumes",
    windows: Optional[List[Tuple[str, int, int]]] = None,
    trials: int = 3,
    results_dir: str = "evaluation/results",
    file_tag: Optional[str] = None,
) -> pd.DataFrame:
    """Executes live scaling benchmark across 1, 2, 4, 6 worker levels against Arctic Shift API."""
    if windows is None:
        windows = DEFAULT_WINDOWS

    commit_hash = get_git_commit()
    curr_iso, default_tag = get_run_timestamp()
    iso_timestamp = curr_iso
    if file_tag is None:
        file_tag = default_tag

    print(f"\n[*] Running Live Scaling Benchmark on r/{subreddit} ({trials} trials, Commit: {commit_hash})...")

    projected_fields = [
        PostField.ID, PostField.TITLE, PostField.SCORE,
        PostField.NUM_COMMENTS, PostField.CREATED_UTC, PostField.SUBREDDIT,
    ]

    records = []
    trial_records = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for label, after_ts, before_ts in windows:
            print(f"    Evaluating live window [{label}] ({after_ts} to {before_ts}) over {trials} trials...")

            trial_times = {w: [] for w in WORKER_LEVELS}
            trial_rams = {w: [] for w in WORKER_LEVELS}
            trial_payloads = {w: [] for w in WORKER_LEVELS}
            trial_latencies = {w: [] for w in WORKER_LEVELS}
            n_posts = 0

            t_idx = 0
            retries_remaining = 3
            while t_idx < trials:
                try:
                    t_run = {
                        "trial": t_idx + 1,
                        "timestamp": iso_timestamp,
                        "git_commit": commit_hash,
                        "window": label,
                    }

                    for w in WORKER_LEVELS:
                        ds_out = os.path.join(tmpdir, f"ds_{after_ts}_trial_{t_idx}_{w}w.parquet")
                        filters = Filters(post_include_fields=projected_fields)
                        scraper = RedditScraper(filters=filters, shard_days=1, post_workers=w)

                        tracemalloc.start()
                        t0 = time.perf_counter()
                        with track_api_calls() as ds_net:
                            posts = scraper.scrape_posts(
                                subreddits=[subreddit],
                                from_dt=after_ts,
                                to_dt=before_ts,
                                output_path=ds_out,
                            )
                        elapsed = time.perf_counter() - t0
                        _, peak_ram = tracemalloc.get_traced_memory()
                        tracemalloc.stop()
                        ds_api = ds_net.summary(wall_clock_sec=elapsed)

                        n_posts = len(posts)
                        trial_times[w].append(elapsed)
                        trial_rams[w].append(peak_ram / (1024 * 1024))
                        trial_payloads[w].append(ds_api["total_payload_kb"])
                        trial_latencies[w].append(ds_api["avg_latency_ms"])

                        t_run[f"time_{w}w_sec"] = round(elapsed, 4)
                        t_run[f"ram_{w}w_mb"] = round(peak_ram / (1024 * 1024), 2)
                        t_run[f"payload_{w}w_kb"] = round(ds_api["total_payload_kb"], 1)

                    t_run["posts"] = n_posts
                    trial_records.append(t_run)

                    print(
                        f"      [Trial {t_idx + 1}/{trials}] "
                        f"1w: {trial_times[1][-1]:.2f}s | 2w: {trial_times[2][-1]:.2f}s | "
                        f"4w: {trial_times[4][-1]:.2f}s | 6w: {trial_times[6][-1]:.2f}s"
                    )
                    t_idx += 1
                except Exception as exc:
                    if retries_remaining > 0:
                        retries_remaining -= 1
                        print(f"      [!] Trial encountered transient network error ({exc}), retrying...")
                        time.sleep(2.0)
                        continue
                    raise

            summary_row = {
                "timestamp": iso_timestamp,
                "git_commit": commit_hash,
                "window": label,
                "posts": n_posts,
                "trials": trials,
            }

            for w in WORKER_LEVELS:
                mean_t = float(np.mean(trial_times[w]))
                sem_t = float(np.std(trial_times[w], ddof=1) / np.sqrt(trials)) if trials > 1 else 0.0
                mean_ram = float(np.mean(trial_rams[w]))
                summary_row[f"time_{w}w_sec"] = round(mean_t, 3)
                summary_row[f"time_{w}w_sem"] = round(sem_t, 3)
                summary_row[f"ram_{w}w_mb"] = round(mean_ram, 2)

            t1 = summary_row["time_1w_sec"]
            summary_row["speedup_2w"] = round(t1 / max(summary_row["time_2w_sec"], 0.001), 2)
            summary_row["speedup_4w"] = round(t1 / max(summary_row["time_4w_sec"], 0.001), 2)
            summary_row["speedup_6w"] = round(t1 / max(summary_row["time_6w_sec"], 0.001), 2)
            summary_row["avg_latency_ms"] = round(float(np.mean(trial_latencies[4])), 1)
            summary_row["payload_kb"] = round(float(np.mean(trial_payloads[4])), 1)
            records.append(summary_row)

            print(
                f"    --> {label} ({n_posts} posts): "
                f"1w={summary_row['time_1w_sec']:.2f}s | 2w={summary_row['time_2w_sec']:.2f}s | "
                f"4w={summary_row['time_4w_sec']:.2f}s | 6w={summary_row['time_6w_sec']:.2f}s"
            )

    df = pd.DataFrame(records)
    trials_df = pd.DataFrame(trial_records)
    fig = render_scaling_chart(
        df,
        title_prefix=f"Live API Benchmark (r/{subreddit})",
        commit_hash=commit_hash,
    )

    csv_path, png_path = save_benchmark_artifacts(
        df=df,
        fig=fig,
        name_prefix="live_scaling",
        results_dir=results_dir,
        file_tag=file_tag,
        trials_df=trials_df,
    )
    plt.close()

    print(f"\n[✓] Saved live scaling summary table to: {csv_path}")
    print(f"[✓] Saved live scaling figure to:        {png_path}")
    return df


def run_scaling_benchmark(
    mode: str = "all",
    windows: Optional[List[Tuple[str, int, int]]] = None,
    dummy_seed: int = 42,
    simulated_latency: float = 0.25,
    subreddit: str = "resumes",
    trials: int = 3,
    results_dir: str = "evaluation/results",
) -> Dict[str, pd.DataFrame]:
    """Unified benchmark runner orchestrating live and synthetic post scaling evaluations."""
    commit_hash = get_git_commit()
    _, file_tag = get_run_timestamp()

    print(f"================================================================================")
    print(f"[*] DEEPSIFT UNIFIED INGESTION BENCHMARK: MODE = {mode.upper()} (Commit: {commit_hash})")
    print(f"    Results Directory: {os.path.join(results_dir, file_tag)}")
    print(f"    Trials Per Bar:    {trials}")
    print(f"================================================================================")

    results = {}
    df_live = None

    if mode in ("all", "live"):
        df_live = run_live_scaling(
            subreddit=subreddit,
            windows=windows,
            trials=trials,
            results_dir=results_dir,
            file_tag=file_tag,
        )
        results["live"] = df_live

    if mode in ("all", "dummy"):
        window_posts = None
        if df_live is not None and not df_live.empty and "window" in df_live.columns and "posts" in df_live.columns:
            window_posts = dict(zip(df_live["window"], df_live["posts"]))

        df_synthetic = run_synthetic_scaling(
            windows=windows,
            dummy_seed=dummy_seed,
            simulated_latency=simulated_latency,
            trials=trials,
            results_dir=results_dir,
            file_tag=file_tag,
            window_post_counts=window_posts,
        )
        results["synthetic"] = df_synthetic

    return results


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
    """Single-window smoke verification test comparing multi-worker execution against 1-worker baseline."""
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

        seq_posts_out = os.path.join(tmpdir, "seq_posts.parquet")
        seq_comments_out = os.path.join(tmpdir, "seq_comments.parquet")
        seq_scraper = RedditScraper(filters=filters, source=source, shard_days=1, post_workers=1, comment_workers=1)

        tracemalloc.start()
        t0_seq = time.perf_counter()
        with track_api_calls() as sq_net:
            seq_posts, seq_comments = seq_scraper.run(
                subreddits=[subreddit],
                from_dt=after_ts,
                to_dt=before_ts,
                posts_output=seq_posts_out,
                comments_output=seq_comments_out,
            )
        elapsed_seq = time.perf_counter() - t0_seq
        _, peak_ram_seq = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        sq_summary = {
            "elapsed_seconds": round(elapsed_seq, 3),
            "peak_memory_mb": round(peak_ram_seq / (1024 * 1024), 2),
            "posts_count": len(seq_posts),
            "comments_count": seq_comments,
            "posts_per_second": round(len(seq_posts) / max(elapsed_seq, 0.001), 1),
            "comments_per_second": round(seq_comments / max(elapsed_seq, 0.001), 1),
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
        f"| **Total Elapsed Time** | {ds['elapsed_seconds']}s | {sq['elapsed_seconds']}s | **{comp['speedup_factor']}x** |",
        f"| **Peak RAM Consumption** | {ds['peak_memory_mb']} MB | {sq['peak_memory_mb']} MB | **{comp['memory_ratio']}x** |",
        f"| **Posts Scraped** | {ds['posts_count']} | {sq['posts_count']} | Matches: {'✓' if comp['posts_count_match'] else '✗'} |",
        f"| **Comments Extracted** | {ds['comments_count']} | {sq['comments_count']} | Matches: {'✓' if comp['comments_count_match'] else '✗'} |",
        f"| **Post Processing Rate** | {ds['posts_per_second']} posts/s | {sq['posts_per_second']} posts/s | {round(ds['posts_per_second'] / max(sq['posts_per_second'], 0.1), 1)}x throughput |",
        f"| **Comment Processing Rate** | {ds['comments_per_second']} comments/s | {sq['comments_per_second']} comments/s | {round(ds['comments_per_second'] / max(sq['comments_per_second'], 0.1), 1)}x throughput |",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="DeepSift Performance Benchmark Runner (Unified Scaling Suite).")
    parser.add_argument("--mode", choices=["all", "dummy", "live", "single"], default="all", help="Execution mode: all (live + dummy scaling), dummy, live, or single window check (default: all)")
    parser.add_argument("--trials", type=int, default=3, help="Number of trials per window (default: 3)")
    parser.add_argument("--latency", type=float, default=0.25, help="Simulated request latency in seconds for dummy source (default: 0.25)")
    parser.add_argument("--subreddit", default="resumes", help="Target subreddit for live evaluation (default: resumes)")
    parser.add_argument("--from-ts", type=int, default=1704150000, help="Epoch timestamp lower bound for single-window check.")
    parser.add_argument("--to-ts", type=int, default=1704153600, help="Epoch timestamp upper bound for single-window check.")
    parser.add_argument("--dummy-posts", type=int, default=100, help="Number of dummy posts for single-window check.")
    parser.add_argument("--dummy-comments", type=int, default=3, help="Number of dummy comments for single-window check.")
    parser.add_argument("--post-workers", type=int, default=4, help="DeepSift shard post workers for single-window check.")
    parser.add_argument("--comment-workers", type=int, default=5, help="DeepSift comment workers for single-window check.")
    parser.add_argument("--markdown", action="store_true", help="Print report in Markdown format for single-window check.")

    args = parser.parse_args()

    if args.mode in ("all", "dummy", "live") and not args.markdown and args.from_ts == 1704150000 and args.to_ts == 1704153600:
        results = run_scaling_benchmark(
            mode=args.mode,
            trials=args.trials,
            simulated_latency=args.latency,
            subreddit=args.subreddit,
        )

        if "live" in results:
            print("\nLive Scaling Summary Table:")
            print(results["live"][["window", "posts", "time_1w_sec", "time_2w_sec", "time_4w_sec", "time_6w_sec", "speedup_6w"]].to_string(index=False))

        if "synthetic" in results:
            print("\nSynthetic Scaling Summary Table:")
            print(results["synthetic"][["window", "posts", "time_1w_sec", "time_2w_sec", "time_4w_sec", "time_6w_sec", "speedup_6w"]].to_string(index=False))
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
