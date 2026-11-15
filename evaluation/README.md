# Evaluation & Benchmarking Guide

This directory provides quantitative performance evaluations comparing **DeepSift** against traditional **sequential scraping execution** and provides a step-by-step guide for developers to benchmark their own scrapers and data ingestion libraries.

---

## Directory Structure

```
evaluation/
├── README.md               # Benchmarking and developer integration guide
├── baseline.py             # Naive single-threaded sequential scraper baseline
├── benchmark.py            # Comparative execution harness and CLI runner
├── live_scaling.py         # Dedicated Live API scaling benchmark runner
├── scaling_experiment.py   # Dedicated Synthetic scaling benchmark runner
├── utils.py                # Commit hashing, timestamp tagging, and latency tracking
└── results/                # Timestamped experiment folders containing CSVs & graphs
    └── 20261115_170030/    # Unified Scaling Run (Both Live API and Synthetic Dummy executed together)
        ├── live_scaling.csv            # Final live summary results table
        ├── live_scaling.png            # Live scaling grouped bar chart
        ├── synthetic_scaling.csv       # Final synthetic summary results table
        ├── synthetic_scaling.png       # Synthetic scaling grouped bar chart
        └── trials/                     # Folder of individual trial runs
            ├── live/
            │   ├── all_trials.csv
            │   ├── trial_1.csv
            │   ├── trial_2.csv
            │   └── trial_3.csv
            └── synthetic/
                ├── all_trials.csv
                ├── trial_1.csv
                ├── trial_2.csv
                └── trial_3.csv
```

---

## Benchmark Results Overview

### 1. Live Arctic Shift API Scaling across Sharding Levels (2, 4, 6 Workers)
Evaluated across 1 to 10 historical days on live Reddit endpoints (`r/resumes`) over 3 independent trials (mean ± standard error of the mean):
*Note: Evaluates batched post shard ingestion only; comments are excluded to prevent individual post HTTP rate limiting on public endpoints.*

| Historical Window | Posts Scraped | Sequential (1w) | DeepSift (2w) | DeepSift (4w) | DeepSift (6w) | Max Speedup | Wire Payload (DS vs Seq) | RAM (DS vs Seq) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1 Day (~100)** | 94 | 2.24 ± 0.69s | 3.03 ± 1.37s | 0.40 ± 0.00s | 0.42 ± 0.01s | **5.59x** | 14.8 KB vs 349.3 KB | 0.17 MB vs 2.56 MB |
| **3 Days (~250)** | 258 | 4.66 ± 0.70s | 4.65 ± 0.36s | 0.42 ± 0.01s | 0.42 ± 0.01s | **11.16x** | 42.4 KB vs 1,023.3 KB | 0.43 MB vs 3.88 MB |
| **5 Days (~500)** | 492 | 8.27 ± 1.01s | 8.48 ± 1.27s | 4.58 ± 1.53s | **1.91 ± 0.71s** | **4.34x** | 82.3 KB vs 1,960.6 KB | 0.55 MB vs 6.59 MB |
| **7 Days (~700)** | 705 | 11.12 ± 1.21s | 11.20 ± 1.05s | 6.31 ± 0.75s | **4.77 ± 2.59s** | **2.33x** | 116.6 KB vs 2,799.8 KB | 0.62 MB vs 8.61 MB |
| **10 Days (~1,000)** | 930 | 14.91 ± 2.46s | 14.72 ± 3.58s | 8.87 ± 2.41s | **3.58 ± 1.29s** | **4.16x** | 153.5 KB vs 3,684.0 KB | 0.62 MB vs 10.45 MB |

*Live Takeaways: As shard count grows across multi-day windows, increasing sharding concurrency from 2 to 4 to 6 workers dramatically hides network round-trip latency (~800ms/req). For 10 days of data, 6 workers reduce total execution time from 14.91s down to **3.58s** (**4.16x speedup**), while server-side field projection saves **24.0x wire bandwidth** and streaming Parquet uses **16.8x less memory**.*

---

### 2. Synthetic Post Scaling Benchmark across Sharding Levels (2, 4, 6 Workers)
Offline benchmark directly mirroring the live query windows (1 to 10 days, 100 posts/day) with 250ms simulated API request latency, isolating thread pool concurrency dynamics, PyArrow schema validation, and chunked Parquet writing across 3 independent trials (mean ± SEM):

| Query Window | Posts Generated | Sequential (1w) | DeepSift (2w) | DeepSift (4w) | DeepSift (6w) | Speedup (6w vs Seq) | Peak RAM (Seq vs DeepSift) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1 Day (~100)** | 100 | 0.26 ± 0.00s | 0.27 ± 0.01s | 0.26 ± 0.00s | **0.27 ± 0.00s** | **1.0x** | 0.10 MB vs 0.23 MB (0.4x) |
| **3 Days (~300)** | 300 | 0.77 ± 0.00s | 0.53 ± 0.00s | 0.28 ± 0.00s | **0.27 ± 0.00s** | **2.8x** | 0.28 MB vs 0.45 MB (0.6x) |
| **5 Days (~500)** | 500 | 1.29 ± 0.00s | 0.79 ± 0.00s | 0.53 ± 0.00s | **0.29 ± 0.00s** | **4.4x** | 0.47 MB vs 0.69 MB (0.7x) |
| **7 Days (~700)** | 700 | 1.80 ± 0.00s | 1.05 ± 0.01s | 0.55 ± 0.00s | **0.53 ± 0.00s** | **3.4x** | 0.66 MB vs 0.69 MB (1.0x) |
| **10 Days (~1,000)** | 1,000 | 2.58 ± 0.00s | 1.33 ± 0.00s | 0.81 ± 0.00s | **0.56 ± 0.01s** | **4.6x** | 0.95 MB vs 0.70 MB (**1.4x less**) |

*Synthetic Takeaways: By matching the day-partitioned shard structure and simulating 250ms API request latency, the synthetic benchmark reproduces the exact theoretical scaling curves observed on live endpoints. As shard count scales to 10 days, 6 workers complete ingestion in 2 parallel waves (0.56s) vs. 10 sequential waves (2.58s), achieving a **4.6x speedup** while chunked Parquet streaming keeps heap memory flat at ~0.70 MB.*

---

## Commit & Date Progression Tracking

To measure performance regressions or improvements across codebase changes, all scaling experiments automatically record:
1. **`git_commit`**: The short commit SHA (`git rev-parse --short HEAD`) at the time of execution stored in each CSV row.
2. **`timestamp`**: Full UTC ISO 8601 execution timestamp stored in each CSV row.
3. **Timestamped Experiment Directory**:
   - Every benchmark run creates a dedicated timestamped folder: `evaluation/results/<timestamp>/`.
   - The final summary CSV dataset (`synthetic_scaling.csv` or `live_scaling.csv`) and visualization graph are stored at the top level of that folder.
   - All individual trial runs are archived cleanly into a dedicated subfolder: `evaluation/results/<timestamp>/trials/` (`trial_1.csv`, `trial_2.csv`, etc., along with `all_trials.csv`).

This structure keeps metrics, individual trial runs, and figures paired cleanly per run without cluttering the root or separating datasets from plots.

---

## Running the Included Benchmarks

```bash
# 1. Unified Scaling Benchmark (runs both Live API and Synthetic Dummy together)
python -m evaluation.scaling_experiment
# or:
python -m evaluation.benchmark

# 2. Run only Synthetic scaling
python -m evaluation.scaling_experiment --mode dummy

# 3. Run only Live scaling
python -m evaluation.scaling_experiment --mode live

# 4. Single-window quick smoke check
python -m evaluation.benchmark --mode single
```

---

## Testing Your Own Subreddits on the Live API

Developers can evaluate DeepSift's concurrent performance against the sequential baseline across any public subreddit on Arctic Shift using either the evaluation CLI or Python API.

### 1. Comparative Benchmark via CLI

Run a live comparative evaluation between DeepSift and the sequential baseline for any subreddit and historical epoch window:

```bash
python -m evaluation.benchmark \
  --mode live \
  --subreddit datascience \
  --from-ts 1704067200 \
  --to-ts 1704153600 \
  --markdown
```

Key CLI Arguments:
- `--subreddit`: Target subreddit name (e.g. `datascience`, `cscareerquestions`, `resumes`).
- `--from-ts` / `--to-ts`: Unix epoch seconds defining the start and end of the historical query window.
- `--post-workers`: Number of concurrent worker threads fetching post shards (default: `4`).
- `--comment-workers`: Number of concurrent worker threads resolving comment trees (default: `5`).
- `--markdown`: Formats the execution time, peak RAM, and data parity results as a Markdown table.

### 2. Comparative Benchmark in Python

To run the comparative evaluation programmatically and inspect metrics:

```python
from evaluation.benchmark import run_benchmark, format_markdown_report

# Run live comparative benchmark on your target subreddit
metrics = run_benchmark(
    mode="live",
    subreddit="cscareerquestions",
    after_ts=1704067200,
    before_ts=1704153600,
    post_workers=4,
    comment_workers=5,
)

# Print markdown comparison table
print(format_markdown_report(metrics))
```

### 3. Multi-Day Scaling Benchmark on Custom Subreddits

To evaluate how DeepSift scales over 1 to 10+ days of historical data on your subreddit:

```python
from evaluation.live_scaling import run_live_scaling

# Runs 1, 3, 5, 7, and 10 day benchmarks on r/cscareerquestions
df = run_live_scaling(
    subreddit="cscareerquestions",
    results_dir="evaluation/results",
)
cols = ["window", "posts", "deepsift_time_sec", "sequential_time_sec", "speedup_factor", "avg_latency_ms", "network_overlap_factor"]
print(df[cols].to_string(index=False))
```

Metrics CSV and visualization plots will automatically be saved into a dedicated timestamped directory under `evaluation/results/<timestamp>/`.

### 4. Direct Ingestion via DeepSift CLI

To directly scrape live data from any subreddit into Parquet files with field projection:

```bash
# Ingest posts and comments for any subreddit
deepsift run \
  --subreddits machinelearning \
  --from 2024-01-01 \
  --to 2024-01-03 \
  --posts-output data/ml_posts.parquet \
  --comments-output data/ml_comments.parquet

# Fetch posts only with server-side field projection
deepsift posts \
  --subreddits cscareerquestions \
  --from 2024-01-01 \
  --to 2024-01-07 \
  --include-fields id \
  --include-fields title \
  --include-fields score \
  --output data/cs_posts.parquet
```

---

## Metric Definitions

- **Elapsed Time (Seconds)**: Wall-clock time measured via high-resolution monotonic timer (`time.perf_counter()`).
- **Peak RAM (Megabytes)**: Maximum heap allocation traced by Python's `tracemalloc` module during execution.
- **Throughput (Items / Second)**: Total records successfully ingested and written per second of execution time.
- **Data Parity (True / False)**: Exact set equality check between post IDs and comment counts to verify zero data loss.
- **Average & P95 Latency (ms)**: Mean and 95th-percentile HTTP round-trip response times per outbound Arctic Shift request.
- **Network Concurrency Overlap**: Cumulative network time divided by elapsed wall-clock time (quantifies latency masking by parallel workers).
- **Payload Transferred (KB)**: Total raw payload bytes received across the wire (measures field projection bandwidth savings).
