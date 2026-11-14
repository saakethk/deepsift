"""
Live API scaling benchmark comparing DeepSift against Sequential scraping on r/resumes.
Evaluates real-world network requests, server projection, and async concurrency across scaling window sizes.
"""
import os
import sys
import time
import pandas as pd

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib_cache"
import matplotlib.pyplot as plt

from evaluation.benchmark import run_benchmark


def run_live_scaling_benchmark(
    subreddit="resumes",
    windows=None,
    output_img="evaluation/live_scaling_graph.png",
    output_csv="evaluation/live_scaling_results.csv",
):
    if windows is None:
        windows = [
            ("30m", 1704151800, 1704153600),
            ("1.0h", 1704150000, 1704153600),
            ("2.0h", 1704146400, 1704153600),
            ("2.9h", 1704143000, 1704153600),
            ("3.8h", 1704140000, 1704153600),
        ]

    records = []
    print(f"[*] Starting live API scaling evaluation on r/{subreddit} across {len(windows)} windows...")

    for label, after_ts, before_ts in windows:
        print(f"    Evaluating window [{label}] ({after_ts} to {before_ts})...")
        res = run_benchmark(
            mode="live",
            subreddit=subreddit,
            after_ts=after_ts,
            before_ts=before_ts,
            post_workers=4,
            comment_workers=5,
        )
        ds = res["deepsift"]
        sq = res["sequential"]
        comp = res["comparison"]

        records.append({
            "window_label": label,
            "posts": ds["posts_count"],
            "comments": ds["comments_count"],
            "total_items": ds["posts_count"] + ds["comments_count"],
            "deepsift_time_sec": ds["elapsed_seconds"],
            "sequential_time_sec": sq["elapsed_seconds"],
            "speedup_factor": comp["speedup_factor"],
            "deepsift_ram_mb": ds["peak_memory_mb"],
            "sequential_ram_mb": sq["peak_memory_mb"],
            "deepsift_comments_per_sec": ds["comments_per_second"],
            "sequential_comments_per_sec": sq["comments_per_second"],
        })
        print(f"      -> {ds['posts_count']} posts, {ds['comments_count']} comments: DeepSift={ds['elapsed_seconds']}s, Seq={sq['elapsed_seconds']}s ({comp['speedup_factor']}x)")

    df = pd.DataFrame(records)

    # Save CSV
    os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)
    df.to_csv(output_csv, index=False)
    print(f"[✓] Live scaling metrics saved to {output_csv}")

    # Generate multi-panel graph
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"Live Arctic Shift API Performance Scaling (r/{subreddit})", fontsize=16, fontweight="bold")

    # 1. Total Elapsed Time
    ax1.plot(df["posts"], df["sequential_time_sec"], "o-", color="#e74c3c", linewidth=2.5, label="Sequential Baseline (Blocking)")
    ax1.plot(df["posts"], df["deepsift_time_sec"], "s-", color="#2ecc71", linewidth=2.5, label="DeepSift (Async Pipelined)")
    ax1.set_title("Live Execution Time (Lower is Better)", fontsize=13, fontweight="semibold")
    ax1.set_xlabel("Number of Real Posts Scraped", fontsize=11)
    ax1.set_ylabel("Execution Time (Seconds)", fontsize=11)
    ax1.grid(True, linestyle="--", alpha=0.6)
    ax1.legend(fontsize=11)

    # 2. Speedup Factor
    ax2.plot(df["posts"], df["speedup_factor"], "d-", color="#3498db", linewidth=2.5)
    ax2.axhline(1.0, color="gray", linestyle=":", label="Baseline (1.0x)")
    ax2.set_title("Speedup Factor (Higher is Better)", fontsize=13, fontweight="semibold")
    ax2.set_xlabel("Number of Real Posts Scraped", fontsize=11)
    ax2.set_ylabel("Speedup Multiplier (x)", fontsize=11)
    ax2.grid(True, linestyle="--", alpha=0.6)
    for _, row in df.iterrows():
        ax2.annotate(f"{row['speedup_factor']:.2f}x", (row["posts"], row["speedup_factor"]),
                     textcoords="offset points", xytext=(0, 7), ha="center", fontsize=9, fontweight="bold")

    # 3. Comment Throughput (Items / Second)
    ax3.plot(df["posts"], df["deepsift_comments_per_sec"], "s-", color="#2ecc71", linewidth=2.5, label="DeepSift")
    ax3.plot(df["posts"], df["sequential_comments_per_sec"], "o-", color="#e74c3c", linewidth=2.5, label="Sequential")
    ax3.set_title("Live Comment Throughput (Higher is Better)", fontsize=13, fontweight="semibold")
    ax3.set_xlabel("Number of Real Posts Scraped", fontsize=11)
    ax3.set_ylabel("Comments / Second", fontsize=11)
    ax3.grid(True, linestyle="--", alpha=0.6)
    ax3.legend(fontsize=11)

    # 4. Peak Memory Consumption
    ax4.plot(df["posts"], df["sequential_ram_mb"], "o-", color="#e74c3c", linewidth=2, label="Sequential Baseline")
    ax4.plot(df["posts"], df["deepsift_ram_mb"], "s-", color="#2ecc71", linewidth=2, label="DeepSift (Parquet Streaming)")
    ax4.set_title("Peak Memory Usage", fontsize=13, fontweight="semibold")
    ax4.set_xlabel("Number of Real Posts Scraped", fontsize=11)
    ax4.set_ylabel("RAM (MB)", fontsize=11)
    ax4.grid(True, linestyle="--", alpha=0.6)
    ax4.legend(fontsize=11)

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    os.makedirs(os.path.dirname(os.path.abspath(output_img)), exist_ok=True)
    plt.savefig(output_img, dpi=300)
    plt.close()
    print(f"[✓] Live scaling graph generated and saved to {output_img}")

    return df


if __name__ == "__main__":
    df = run_live_scaling_benchmark()
    print("\nLive Summary Results:")
    print(df[["window_label", "posts", "comments", "deepsift_time_sec", "sequential_time_sec", "speedup_factor"]].to_string(index=False))
