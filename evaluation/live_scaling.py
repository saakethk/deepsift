"""
Live Arctic Shift API scaling experiment: Evaluates DeepSift across
sharding concurrency levels (2, 4, 6 workers) vs. sequential baseline (1 worker)
across multi-day historical query windows (1 to 10 days on r/resumes).
Captures API round-trip latencies, memory footprint, wire payload, and execution times with error bars.
"""
import os
import sys
import time
import argparse
import tempfile
import tracemalloc
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib_cache"
import matplotlib.pyplot as plt

from deepsift.scraper import RedditScraper
from deepsift.filters import Filters
from deepsift.models import PostField
from evaluation.baseline import SequentialScraper
from evaluation.utils import get_git_commit, get_run_timestamp, save_benchmark_artifacts, track_api_calls


DEFAULT_WINDOWS = [
    ("1 Day (~100)", 1704067200, 1704153600),
    ("3 Days (~250)", 1703894400, 1704153600),
    ("5 Days (~500)", 1703721600, 1704153600),
    ("7 Days (~700)", 1703548800, 1704153600),
    ("10 Days (~1000)", 1703289600, 1704153600),
]
WORKER_LEVELS = [2, 4, 6]


def render_live_scaling_chart(df: pd.DataFrame, commit_hash: str = "latest", subreddit: str = "resumes") -> plt.Figure:
    """Renders grouped bar comparison across sequential baseline and 2, 4, 6 sharding workers with SEM error bars."""
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig, ax = plt.subplots(figsize=(12.5, 6.2), facecolor="#ffffff")

    windows = df["window"].tolist()
    posts = df["posts"].tolist()
    labels = [f"{w.split(' ')[0]} {w.split(' ')[1]}\n({p} posts)" for w, p in zip(windows, posts)]
    x = np.arange(len(labels))
    width = 0.19

    trials_count = int(df["trials"].iloc[0]) if "trials" in df.columns else 1
    trials_note = f" • {trials_count} Trials (Mean ± SEM)" if trials_count > 1 else ""

    rects_seq = ax.bar(
        x - 1.5 * width,
        df["sequential_time_sec"],
        width,
        yerr=df.get("sequential_time_sem"),
        capsize=3,
        error_kw=dict(ecolor="#7f1d1d", lw=1.2, capthick=1.2),
        label="Sequential Baseline (1 Worker)",
        color="#ef4444",
        edgecolor="#b91c1c",
        alpha=0.9,
    )
    rects_2w = ax.bar(
        x - 0.5 * width,
        df["deepsift_2w_time_sec"],
        width,
        yerr=df.get("deepsift_2w_time_sem"),
        capsize=3,
        error_kw=dict(ecolor="#0284c7", lw=1.2, capthick=1.2),
        label="DeepSift (2 Shard Workers)",
        color="#38bdf8",
        edgecolor="#0284c7",
        alpha=0.9,
    )
    rects_4w = ax.bar(
        x + 0.5 * width,
        df["deepsift_4w_time_sec"],
        width,
        yerr=df.get("deepsift_4w_time_sem"),
        capsize=3,
        error_kw=dict(ecolor="#047857", lw=1.2, capthick=1.2),
        label="DeepSift (4 Shard Workers)",
        color="#10b981",
        edgecolor="#047857",
        alpha=0.9,
    )
    rects_6w = ax.bar(
        x + 1.5 * width,
        df["deepsift_6w_time_sec"],
        width,
        yerr=df.get("deepsift_6w_time_sem"),
        capsize=3,
        error_kw=dict(ecolor="#4338ca", lw=1.2, capthick=1.2),
        label="DeepSift (6 Shard Workers)",
        color="#6366f1",
        edgecolor="#4338ca",
        alpha=0.9,
    )

    ax.set_title(
        f"DeepSift vs. Sequential Baseline: Live API Post Ingestion Across Sharding Levels (2, 4, 6 Workers)\n"
        f"Wall-Clock Execution Time Across Multi-Day Post Windows (r/{subreddit}){trials_note} • Commit: {commit_hash}",
        fontsize=12,
        fontweight="bold",
        pad=14,
        color="#0f172a",
    )
    ax.set_ylabel("Execution Time (Seconds)", fontsize=10.5, fontweight="semibold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9.5)
    ax.grid(True, linestyle="--", alpha=0.5, axis="y")

    all_groups = [
        (rects_seq, df.get("sequential_time_sem"), "#991b1b"),
        (rects_2w, df.get("deepsift_2w_time_sem"), "#0369a1"),
        (rects_4w, df.get("deepsift_4w_time_sem"), "#065f46"),
        (rects_6w, df.get("deepsift_6w_time_sem"), "#3730a3"),
    ]

    max_top = 0.0
    for rects, sems, color in all_groups:
        for i, rect in enumerate(rects):
            h = rect.get_height()
            err = float(sems.iloc[i]) if sems is not None else 0.0
            top = h + err
            max_top = max(max_top, top)

            label_text = f"{h:.1f}±{err:.1f}s" if err > 0.05 else f"{h:.1f}s"
            ax.text(
                rect.get_x() + rect.get_width() / 2,
                top + 0.3,
                label_text,
                ha="center",
                va="bottom",
                fontsize=7.2,
                fontweight="bold",
                color=color,
            )

    ax.set_ylim(0, max_top * 1.22)
    ax.legend(loc="upper left", frameon=True, facecolor="#ffffff", framealpha=0.9, fontsize=9)
    fig.tight_layout()
    return fig


def run_live_scaling(
    subreddit: str = "resumes",
    windows = None,
    trials: int = 3,
    results_dir: str = "evaluation/results",
    file_tag: str = None,
) -> pd.DataFrame:
    if windows is None:
        windows = DEFAULT_WINDOWS

    records = []
    trial_records = []
    commit_hash = get_git_commit()
    curr_iso, default_tag = get_run_timestamp()
    iso_timestamp = curr_iso
    if file_tag is None:
        file_tag = default_tag

    print(f"[*] Starting live scaling evaluation on r/{subreddit} (Commit: {commit_hash}, Trials: {trials}, Worker Levels: {WORKER_LEVELS})...")

    projected_fields = [
        PostField.ID, PostField.TITLE, PostField.SCORE,
        PostField.NUM_COMMENTS, PostField.CREATED_UTC, PostField.SUBREDDIT,
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        for label, after_ts, before_ts in windows:
            print(f"    Evaluating window [{label}] ({after_ts} to {before_ts}) over {trials} trials...")

            seq_times = []
            seq_rams = []
            seq_payloads = []

            worker_trial_times = {w: [] for w in WORKER_LEVELS}
            worker_trial_rams = {w: [] for w in WORKER_LEVELS}
            worker_trial_payloads = {w: [] for w in WORKER_LEVELS}
            worker_trial_latencies = {w: [] for w in WORKER_LEVELS}

            n_posts = 0

            t_idx = 0
            retries_remaining = 3
            while t_idx < trials:
                try:
                    # Sequential baseline execution
                    seq = SequentialScraper(source_type="arctic_shift")
                    tracemalloc.start()
                    t0_seq = time.perf_counter()
                    with track_api_calls() as sq_net:
                        posts_seq = seq.scrape_posts(
                            subreddit=subreddit,
                            after_ts=after_ts,
                            before_ts=before_ts,
                        )
                    seq_time = time.perf_counter() - t0_seq
                    _, seq_peak_ram = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    sq_api = sq_net.summary(wall_clock_sec=seq_time)

                    seq_times.append(seq_time)
                    seq_rams.append(seq_peak_ram / (1024 * 1024))
                    seq_payloads.append(sq_api["total_payload_kb"])
                    n_posts = len(posts_seq)

                    # DeepSift across worker levels
                    for w in WORKER_LEVELS:
                        ds_out = os.path.join(tmpdir, f"ds_{after_ts}_trial_{t_idx}_{w}w.parquet")
                        filters = Filters(post_include_fields=projected_fields)
                        scraper = RedditScraper(filters=filters, shard_days=1, post_workers=w)

                        tracemalloc.start()
                        t0 = time.perf_counter()
                        with track_api_calls() as ds_net:
                            posts_ds = scraper.scrape_posts(
                                subreddits=[subreddit],
                                from_dt=after_ts,
                                to_dt=before_ts,
                                output_path=ds_out,
                            )
                        ds_time = time.perf_counter() - t0
                        _, ds_peak_ram = tracemalloc.get_traced_memory()
                        tracemalloc.stop()
                        ds_api = ds_net.summary(wall_clock_sec=ds_time)

                        worker_trial_times[w].append(ds_time)
                        worker_trial_rams[w].append(ds_peak_ram / (1024 * 1024))
                        worker_trial_payloads[w].append(ds_api["total_payload_kb"])
                        worker_trial_latencies[w].append(ds_api["avg_latency_ms"])

                    trial_records.append({
                        "trial": t_idx + 1,
                        "timestamp": iso_timestamp,
                        "git_commit": commit_hash,
                        "window": label,
                        "posts": n_posts,
                        "sequential_time_sec": round(seq_time, 4),
                        "sequential_ram_mb": round(seq_peak_ram / (1024 * 1024), 2),
                        "sequential_payload_kb": round(sq_api["total_payload_kb"], 1),
                        "deepsift_2w_time_sec": round(worker_trial_times[2][-1], 4),
                        "deepsift_2w_ram_mb": round(worker_trial_rams[2][-1], 2),
                        "deepsift_2w_payload_kb": round(worker_trial_payloads[2][-1], 1),
                        "deepsift_4w_time_sec": round(worker_trial_times[4][-1], 4),
                        "deepsift_4w_ram_mb": round(worker_trial_rams[4][-1], 2),
                        "deepsift_4w_payload_kb": round(worker_trial_payloads[4][-1], 1),
                        "deepsift_6w_time_sec": round(worker_trial_times[6][-1], 4),
                        "deepsift_6w_ram_mb": round(worker_trial_rams[6][-1], 2),
                        "deepsift_6w_payload_kb": round(worker_trial_payloads[6][-1], 1),
                    })

                    print(f"      [Trial {t_idx + 1}/{trials}] Seq: {seq_time:.2f}s | DS(2w): {worker_trial_times[2][-1]:.2f}s | DS(4w): {worker_trial_times[4][-1]:.2f}s | DS(6w): {worker_trial_times[6][-1]:.2f}s")
                    t_idx += 1
                except Exception as exc:
                    if retries_remaining > 0:
                        retries_remaining -= 1
                        print(f"      [!] Trial encountered transient error ({exc}), retrying...")
                        time.sleep(2.0)
                        continue
                    raise

            seq_mean = float(np.mean(seq_times))
            seq_std = float(np.std(seq_times, ddof=1)) if trials > 1 else 0.0
            seq_sem = seq_std / np.sqrt(trials) if trials > 1 else 0.0

            w_stats = {}
            for w in WORKER_LEVELS:
                w_mean = float(np.mean(worker_trial_times[w]))
                w_std = float(np.std(worker_trial_times[w], ddof=1)) if trials > 1 else 0.0
                w_sem = w_std / np.sqrt(trials) if trials > 1 else 0.0
                w_stats[w] = (w_mean, w_std, w_sem)

            records.append({
                "timestamp": iso_timestamp,
                "git_commit": commit_hash,
                "window": label,
                "posts": n_posts,
                "trials": trials,
                "sequential_time_sec": round(seq_mean, 3),
                "sequential_time_std": round(seq_std, 3),
                "sequential_time_sem": round(seq_sem, 3),
                "deepsift_2w_time_sec": round(w_stats[2][0], 3),
                "deepsift_2w_time_std": round(w_stats[2][1], 3),
                "deepsift_2w_time_sem": round(w_stats[2][2], 3),
                "deepsift_4w_time_sec": round(w_stats[4][0], 3),
                "deepsift_4w_time_std": round(w_stats[4][1], 3),
                "deepsift_4w_time_sem": round(w_stats[4][2], 3),
                "deepsift_6w_time_sec": round(w_stats[6][0], 3),
                "deepsift_6w_time_std": round(w_stats[6][1], 3),
                "deepsift_6w_time_sem": round(w_stats[6][2], 3),
                "speedup_2w": round(seq_mean / max(w_stats[2][0], 0.001), 2),
                "speedup_4w": round(seq_mean / max(w_stats[4][0], 0.001), 2),
                "speedup_6w": round(seq_mean / max(w_stats[6][0], 0.001), 2),
                "sequential_ram_mb": round(float(np.mean(seq_rams)), 2),
                "deepsift_ram_mb": round(float(np.mean(worker_trial_rams[4])), 2),
                "avg_latency_ms": round(float(np.mean(worker_trial_latencies[4])), 1),
                "deepsift_payload_kb": round(float(np.mean(worker_trial_payloads[4])), 1),
                "sequential_payload_kb": round(float(np.mean(seq_payloads)), 1),
            })
            print(f"    --> {label} ({n_posts} posts): Seq={seq_mean:.2f}s | DS(2w)={w_stats[2][0]:.2f}s | DS(4w)={w_stats[4][0]:.2f}s | DS(6w)={w_stats[6][0]:.2f}s")

    df = pd.DataFrame(records)
    trials_df = pd.DataFrame(trial_records)
    fig = render_live_scaling_chart(df, commit_hash=commit_hash, subreddit=subreddit)

    csv_path, png_path = save_benchmark_artifacts(
        df=df,
        fig=fig,
        name_prefix="live_scaling",
        results_dir=results_dir,
        file_tag=file_tag,
        trials_df=trials_df,
    )
    plt.close()

    print(f"\n[✓] Saved final live scaling summary table to: {csv_path}")
    print(f"[✓] Saved individual trial runs to:             {os.path.join(results_dir, file_tag, 'trials', 'live')}")
    print(f"[✓] Saved live scaling figure to:                {png_path}")

    return df


def main():
    parser = argparse.ArgumentParser(description="Live Arctic Shift API scaling benchmark across sharding levels.")
    parser.add_argument("--subreddit", default="resumes", help="Target subreddit for live evaluation.")
    parser.add_argument("--trials", type=int, default=3, help="Number of trials per window to compute standard error.")
    args = parser.parse_args()

    df = run_live_scaling(subreddit=args.subreddit, trials=args.trials)
    print("\nLive Scaling Summary Results:")
    print(df[["window", "posts", "trials", "sequential_time_sec", "deepsift_2w_time_sec", "deepsift_4w_time_sec", "deepsift_6w_time_sec", "speedup_4w", "speedup_6w"]].to_string(index=False))


if __name__ == "__main__":
    main()
