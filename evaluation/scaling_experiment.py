"""
Unified scaling benchmark suite: Evaluates DeepSift against sequential execution
across identical multi-day query windows (1 to 10 days) and sharding concurrency levels (2, 4, 6 workers)
running both live Arctic Shift API and synthetic dummy benchmarks together.
"""
import os
import sys
import time
import argparse
import tempfile
import tracemalloc
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib_cache"
import matplotlib.pyplot as plt

from deepsift.scraper import RedditScraper
from deepsift.sources.dummy import DummySource
from deepsift.filters import Filters
from evaluation.baseline import SequentialScraper
from evaluation.live_scaling import run_live_scaling
from evaluation.utils import get_git_commit, get_run_timestamp, save_benchmark_artifacts


DEFAULT_WINDOWS = [
    ("1 Day (~100)", 1704067200, 1704153600),
    ("3 Days (~300)", 1703894400, 1704153600),
    ("5 Days (~500)", 1703721600, 1704153600),
    ("7 Days (~700)", 1703548800, 1704153600),
    ("10 Days (~1000)", 1703289600, 1704153600),
]
WORKER_LEVELS = [2, 4, 6]


def render_synthetic_scaling_chart(df: pd.DataFrame, commit_hash: str = "latest") -> plt.Figure:
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
        f"DeepSift vs. Sequential Baseline: Synthetic Post Ingestion Across Sharding Levels (2, 4, 6 Workers)\n"
        f"Wall-Clock Execution Time Across Multi-Day Query Windows{trials_note} • Commit: {commit_hash}",
        fontsize=12,
        fontweight="bold",
        pad=14,
        color="#0f172a",
    )
    ax.set_ylabel("Execution Time (Seconds)", fontsize=10.5, fontweight="semibold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9.5)
    ax.grid(True, linestyle="--", alpha=0.5, axis="y")

    all_rects = [rects_seq, rects_2w, rects_4w, rects_6w]
    colors = ["#991b1b", "#0369a1", "#065f46", "#3730a3"]

    max_val = 0.0
    for r_group, c in zip(all_rects, colors):
        for rect in r_group:
            h = rect.get_height()
            max_val = max(max_val, h)
            if h >= 0.01:
                ax.text(
                    rect.get_x() + rect.get_width() / 2,
                    h + 0.04,
                    f"{h:.2f}s",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                    fontweight="bold",
                    color=c,
                )

    ax.set_ylim(0, max_val * 1.25)
    ax.legend(loc="upper left", frameon=True, facecolor="#ffffff", framealpha=0.9, fontsize=9)
    fig.tight_layout()
    return fig


def run_synthetic_scaling(
    windows=None,
    dummy_seed: int = 42,
    simulated_latency: float = 0.25,
    trials: int = 3,
    results_dir: str = "evaluation/results",
    file_tag: Optional[str] = None,
) -> pd.DataFrame:
    """Executes synthetic scaling benchmark across multi-day windows and worker levels (2, 4, 6) with simulated latency."""
    if windows is None:
        windows = DEFAULT_WINDOWS

    commit_hash = get_git_commit()
    curr_iso, default_tag = get_run_timestamp()
    iso_timestamp = curr_iso
    if file_tag is None:
        file_tag = default_tag

    print(f"\n[*] Running Synthetic Scaling Benchmark ({trials} trials, {simulated_latency*1000:.0f}ms simulated latency, Commit: {commit_hash})...")

    records = []
    trial_records = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for label, after_ts, before_ts in windows:
            print(f"    Evaluating synthetic window: {label}...")

            trial_seq_times = []
            trial_ds_times = {w: [] for w in WORKER_LEVELS}
            trial_seq_rams = []
            trial_ds_rams = {w: [] for w in WORKER_LEVELS}
            posts_count = 0

            for trial in range(1, trials + 1):
                seq = SequentialScraper(
                    source_type="dummy",
                    dummy_seed=dummy_seed + trial,
                    simulated_latency=simulated_latency,
                )
                tracemalloc.start()
                t0_seq = time.perf_counter()
                posts_seq = seq.scrape_posts(
                    subreddit="resumes",
                    after_ts=after_ts,
                    before_ts=before_ts,
                    dummy_posts_per_shard=100,
                )
                seq_time = time.perf_counter() - t0_seq
                _, seq_ram = tracemalloc.get_traced_memory()
                tracemalloc.stop()

                trial_seq_times.append(seq_time)
                trial_seq_rams.append(seq_ram / (1024 * 1024))
                posts_count = len(posts_seq)

                t_ds_times = {}
                t_ds_rams = {}

                for w in WORKER_LEVELS:
                    ds_out = os.path.join(tmpdir, f"ds_{before_ts}_{w}w_t{trial}.parquet")
                    scraper = RedditScraper(
                        filters=Filters(),
                        source=DummySource(
                            posts_per_shard=100,
                            batch_size=100,
                            seed=dummy_seed + trial,
                            simulated_latency=simulated_latency,
                        ),
                        shard_days=1,
                        post_workers=w,
                    )
                    tracemalloc.start()
                    t0_ds = time.perf_counter()
                    posts_ds = scraper.scrape_posts(
                        subreddits=["resumes"],
                        from_dt=after_ts,
                        to_dt=before_ts,
                        output_path=ds_out,
                    )
                    ds_time = time.perf_counter() - t0_ds
                    _, ds_ram = tracemalloc.get_traced_memory()
                    tracemalloc.stop()

                    trial_ds_times[w].append(ds_time)
                    trial_ds_rams[w].append(ds_ram / (1024 * 1024))
                    t_ds_times[w] = ds_time
                    t_ds_rams[w] = ds_ram / (1024 * 1024)

                trial_records.append({
                    "trial": trial,
                    "timestamp": iso_timestamp,
                    "git_commit": commit_hash,
                    "window": label,
                    "posts": posts_count,
                    "sequential_time_sec": round(seq_time, 4),
                    "sequential_ram_mb": round(seq_ram / (1024 * 1024), 2),
                    "deepsift_2w_time_sec": round(t_ds_times[2], 4),
                    "deepsift_2w_ram_mb": round(t_ds_rams[2], 2),
                    "deepsift_4w_time_sec": round(t_ds_times[4], 4),
                    "deepsift_4w_ram_mb": round(t_ds_rams[4], 2),
                    "deepsift_6w_time_sec": round(t_ds_times[6], 4),
                    "deepsift_6w_ram_mb": round(t_ds_rams[6], 2),
                })

            mean_seq_time = float(np.mean(trial_seq_times))
            sem_seq_time = float(np.std(trial_seq_times, ddof=1) / np.sqrt(trials)) if trials > 1 else 0.0
            mean_seq_ram = float(np.mean(trial_seq_rams))

            mean_ds_times = {}
            sem_ds_times = {}
            mean_ds_rams = {}
            for w in WORKER_LEVELS:
                mean_ds_times[w] = float(np.mean(trial_ds_times[w]))
                sem_ds_times[w] = float(np.std(trial_ds_times[w], ddof=1) / np.sqrt(trials)) if trials > 1 else 0.0
                mean_ds_rams[w] = float(np.mean(trial_ds_rams[w]))

            records.append({
                "timestamp": iso_timestamp,
                "git_commit": commit_hash,
                "window": label,
                "trials": trials,
                "posts": posts_count,
                "sequential_time_sec": round(mean_seq_time, 3),
                "sequential_time_sem": round(sem_seq_time, 3),
                "deepsift_2w_time_sec": round(mean_ds_times[2], 3),
                "deepsift_2w_time_sem": round(sem_ds_times[2], 3),
                "deepsift_4w_time_sec": round(mean_ds_times[4], 3),
                "deepsift_4w_time_sem": round(sem_ds_times[4], 3),
                "deepsift_6w_time_sec": round(mean_ds_times[6], 3),
                "deepsift_6w_time_sem": round(sem_ds_times[6], 3),
                "speedup_2w": round(mean_seq_time / max(mean_ds_times[2], 0.001), 2),
                "speedup_4w": round(mean_seq_time / max(mean_ds_times[4], 0.001), 2),
                "speedup_6w": round(mean_seq_time / max(mean_ds_times[6], 0.001), 2),
                "sequential_ram_mb": round(mean_seq_ram, 2),
                "deepsift_ram_mb": round(mean_ds_rams[4], 2),
            })
            print(
                f"      -> {label} ({posts_count} posts): "
                f"Seq={mean_seq_time:.2f}s | DS(2w)={mean_ds_times[2]:.2f}s | "
                f"DS(4w)={mean_ds_times[4]:.2f}s | DS(6w)={mean_ds_times[6]:.2f}s"
            )

    df = pd.DataFrame(records)
    trials_df = pd.DataFrame(trial_records)
    fig = render_synthetic_scaling_chart(df, commit_hash=commit_hash)

    csv_path, png_path = save_benchmark_artifacts(
        df=df,
        fig=fig,
        name_prefix="synthetic_scaling",
        results_dir=results_dir,
        file_tag=file_tag,
        trials_df=trials_df,
    )
    plt.close()

    print(f"\n[✓] Saved final synthetic scaling summary table to: {csv_path}")
    print(f"[✓] Saved individual synthetic trial runs to:         {os.path.join(results_dir, file_tag, 'trials', 'synthetic')}")
    print(f"[✓] Saved synthetic scaling figure to:               {png_path}")

    return df


def run_scaling_benchmark(
    mode: str = "all",
    windows=None,
    dummy_seed: int = 42,
    simulated_latency: float = 0.25,
    subreddit: str = "resumes",
    trials: int = 3,
    results_dir: str = "evaluation/results",
) -> Dict[str, pd.DataFrame]:
    """Unified benchmark runner: executes both live and dummy scaling evaluations together."""
    commit_hash = get_git_commit()
    _, file_tag = get_run_timestamp()

    print(f"================================================================================")
    print(f"[*] DEEPSIFT UNIFIED INGESTION BENCHMARK: MODE = {mode.upper()} (Commit: {commit_hash})")
    print(f"    Results Directory: {os.path.join(results_dir, file_tag)}")
    print(f"    Trials Per Bar:    {trials}")
    print(f"================================================================================")

    results = {}
    df_synthetic = None
    df_live = None

    if mode in ("all", "dummy"):
        df_synthetic = run_synthetic_scaling(
            windows=windows,
            dummy_seed=dummy_seed,
            simulated_latency=simulated_latency,
            trials=trials,
            results_dir=results_dir,
            file_tag=file_tag,
        )
        results["synthetic"] = df_synthetic

    if mode in ("all", "live"):
        df_live = run_live_scaling(
            subreddit=subreddit,
            windows=windows,
            trials=trials,
            results_dir=results_dir,
            file_tag=file_tag,
        )
        results["live"] = df_live

    return results


def main():
    parser = argparse.ArgumentParser(description="Unified post ingestion scaling benchmark (Live + Dummy).")
    parser.add_argument("--mode", choices=["all", "dummy", "live"], default="all", help="Evaluation mode: all (runs live + dummy together), dummy, or live (default: all)")
    parser.add_argument("--trials", type=int, default=3, help="Number of trials per evaluation window (default: 3)")
    parser.add_argument("--latency", type=float, default=0.25, help="Simulated request latency in seconds for dummy source (default: 0.25)")
    parser.add_argument("--subreddit", default="resumes", help="Target subreddit for live evaluation (default: resumes)")
    args = parser.parse_args()

    results = run_scaling_benchmark(
        mode=args.mode,
        trials=args.trials,
        simulated_latency=args.latency,
        subreddit=args.subreddit,
    )

    if "synthetic" in results:
        print("\n--- Synthetic Scaling Summary Table ---")
        print(results["synthetic"][["window", "posts", "sequential_time_sec", "deepsift_2w_time_sec", "deepsift_4w_time_sec", "deepsift_6w_time_sec", "speedup_6w"]].to_string(index=False))

    if "live" in results:
        print("\n--- Live Scaling Summary Table ---")
        print(results["live"][["window", "posts", "sequential_time_sec", "deepsift_2w_time_sec", "deepsift_4w_time_sec", "deepsift_6w_time_sec", "speedup_6w"]].to_string(index=False))


if __name__ == "__main__":
    main()
