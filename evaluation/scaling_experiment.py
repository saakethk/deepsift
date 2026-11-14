"""
Scaling benchmark script comparing DeepSift to Sequential execution across multiple post volumes.
Generates empirical benchmark results and visualizes performance curves via Matplotlib.
"""
import os
import sys
import time
import tracemalloc

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

# Set Matplotlib cache dir to /tmp to avoid permission warnings on mac
os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib_cache"
import matplotlib.pyplot as plt

from evaluation.benchmark import run_benchmark


def run_scaling_benchmark(
    post_counts=None,
    comments_per_post=5,
    dummy_seed=42,
    output_img="evaluation/scaling_benchmark_graph.png",
    output_csv="evaluation/scaling_results.csv",
):
    if post_counts is None:
        post_counts = [100, 250, 500, 1000, 2000, 3500, 5000]

    # Warm-up run to eliminate one-time C++ PyArrow initialization bias
    _ = run_benchmark(mode="dummy", dummy_posts=50, dummy_comments_per_post=2)

    records = []
    print("[*] Running scaling evaluation across post volumes...")

    for n in post_counts:
        print(f"    Evaluating N={n:,} posts...")
        res = run_benchmark(
            mode="dummy",
            dummy_posts=n,
            dummy_comments_per_post=comments_per_post,
            dummy_seed=dummy_seed,
            post_workers=4,
            comment_workers=5,
        )
        ds = res["deepsift"]
        sq = res["sequential"]
        comp = res["comparison"]

        records.append({
            "posts": n,
            "comments": ds["comments_count"],
            "total_items": n + ds["comments_count"],
            "deepsift_time_sec": ds["elapsed_seconds"],
            "sequential_time_sec": sq["elapsed_seconds"],
            "speedup_factor": comp["speedup_factor"],
            "deepsift_ram_mb": ds["peak_memory_mb"],
            "sequential_ram_mb": sq["peak_memory_mb"],
            "deepsift_comments_per_sec": ds["comments_per_second"],
            "sequential_comments_per_sec": sq["comments_per_second"],
        })

    df = pd.DataFrame(records)

    # Save CSV
    os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)
    df.to_csv(output_csv, index=False)
    print(f"[✓] Benchmark metrics saved to {output_csv}")

    # Generate multi-panel graph
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("DeepSift vs Sequential Execution Performance Scaling", fontsize=16, fontweight="bold")

    # 1. Total Elapsed Time
    ax1.plot(df["posts"], df["sequential_time_sec"], "o-", color="#e74c3c", linewidth=2, label="Sequential Baseline")
    ax1.plot(df["posts"], df["deepsift_time_sec"], "s-", color="#2ecc71", linewidth=2.5, label="DeepSift (Pipelined)")
    ax1.set_title("Total Execution Time (Lower is Better)", fontsize=13, fontweight="semibold")
    ax1.set_xlabel("Number of Posts Scraped", fontsize=11)
    ax1.set_ylabel("Execution Time (Seconds)", fontsize=11)
    ax1.grid(True, linestyle="--", alpha=0.6)
    ax1.legend(fontsize=11)

    # 2. Speedup Factor
    ax2.plot(df["posts"], df["speedup_factor"], "d-", color="#3498db", linewidth=2.5)
    ax2.axhline(1.0, color="gray", linestyle=":", label="Baseline (1.0x)")
    ax2.set_title("Speedup Factor (Higher is Better)", fontsize=13, fontweight="semibold")
    ax2.set_xlabel("Number of Posts Scraped", fontsize=11)
    ax2.set_ylabel("Speedup Multiplier (x)", fontsize=11)
    ax2.grid(True, linestyle="--", alpha=0.6)
    for _, row in df.iterrows():
        ax2.annotate(f"{row['speedup_factor']:.1f}x", (row["posts"], row["speedup_factor"]),
                     textcoords="offset points", xytext=(0, 7), ha="center", fontsize=9, fontweight="bold")

    # 3. Comment Throughput (Items / Second)
    ax3.plot(df["posts"], df["deepsift_comments_per_sec"], "s-", color="#2ecc71", linewidth=2, label="DeepSift")
    ax3.plot(df["posts"], df["sequential_comments_per_sec"], "o-", color="#e74c3c", linewidth=2, label="Sequential")
    ax3.set_title("Comment Processing Throughput (Higher is Better)", fontsize=13, fontweight="semibold")
    ax3.set_xlabel("Number of Posts Scraped", fontsize=11)
    ax3.set_ylabel("Comments / Second", fontsize=11)
    ax3.grid(True, linestyle="--", alpha=0.6)
    ax3.legend(fontsize=11)

    # 4. Peak Memory Consumption
    ax4.plot(df["posts"], df["sequential_ram_mb"], "o-", color="#e74c3c", linewidth=2, label="Sequential (In-Memory Heap)")
    ax4.plot(df["posts"], df["deepsift_ram_mb"], "s-", color="#2ecc71", linewidth=2, label="DeepSift (Streaming Parquet)")
    ax4.set_title("Peak Memory Usage", fontsize=13, fontweight="semibold")
    ax4.set_xlabel("Number of Posts Scraped", fontsize=11)
    ax4.set_ylabel("RAM (MB)", fontsize=11)
    ax4.grid(True, linestyle="--", alpha=0.6)
    ax4.legend(fontsize=11)

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    os.makedirs(os.path.dirname(os.path.abspath(output_img)), exist_ok=True)
    plt.savefig(output_img, dpi=300)
    plt.close()
    print(f"[✓] Scaling graph generated and saved to {output_img}")

    return df


if __name__ == "__main__":
    df = run_scaling_benchmark()
    print("\nSummary Results:")
    print(df[["posts", "comments", "deepsift_time_sec", "sequential_time_sec", "speedup_factor"]].to_string(index=False))
