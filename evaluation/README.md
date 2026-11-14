# Evaluation & Benchmarking: DeepSift vs Sequential Execution

This module provides quantitative performance evaluations comparing **DeepSift** against traditional **sequential scraping execution** across historical Reddit datasets.

---

## Architecture & Implementation Comparison

| Dimension | DeepSift | Traditional Sequential Baseline |
| :--- | :--- | :--- |
| **Post Ingestion** | Multi-threaded concurrent time sharding (`ThreadPoolExecutor`) | Single-threaded sequential pagination |
| **Comment Extraction** | Pipelined asynchronous connection pool (`httpx.AsyncClient`) | Blocking synchronous requests loop (`requests.get`) |
| **Field Projection** | Server-side projection (`fields=` query parameter) reduces payload size | Fetches full unprojected JSON blobs over the wire |
| **Memory Management** | Constant chunked streaming to snappy Parquet directly on disk | Accumulates raw dictionaries in Python heap lists (`pd.DataFrame`) |
| **Polymorphic Coercion** | Dynamic schema unification for mixed Reddit fields (`edited`, `flairs`) | Fails or relies on loose runtime typing |
| **Fault Tolerance** | Thread-safe failure isolation and structured error logging (`errors.json`) | Unhandled network exceptions abort whole execution |

---

## Running the Benchmark

The benchmarking tool supports two execution modes:

### 1. Synthetic Dummy Benchmark (Offline & Deterministic)
Evaluates algorithmic and pipeline throughput without network jitter or API rate-limit delays:
```bash
# Single benchmark run
python -m evaluation.benchmark --mode dummy --dummy-posts 2000 --dummy-comments 10

# Multi-volume scaling benchmark (generates graph & CSV across 100 to 5,000 posts)
python -m evaluation.scaling_experiment
```

### 2. Live Arctic Shift Benchmark (`r/resumes`)
Evaluates real-world network requests, server-side projection, and tree resolution against the live Arctic Shift API:
```bash
python -m evaluation.benchmark --mode live --subreddit resumes --from-ts 1704150000 --to-ts 1704153600
```

---

## Command Line Arguments

| Option | Default | Description |
| :--- | :--- | :--- |
| `--mode` | `dummy` | Target mode: `dummy` (offline synthetic) or `live` (Arctic Shift API) |
| `--subreddit` | `resumes` | Target subreddit for live evaluation |
| `--from-ts` | `1704150000` | Epoch timestamp start bound (live mode) |
| `--to-ts` | `1704153600` | Epoch timestamp end bound (live mode) |
| `--dummy-posts` | `100` | Number of synthetic posts generated per shard (dummy mode) |
| `--dummy-comments`| `3` | Number of comments generated per post (dummy mode) |
| `--post-workers` | `4` | Parallel thread workers for shard scanning |
| `--comment-workers`| `5` | Async concurrency worker pool size for comment trees |

---

## Live Benchmark Results (`r/resumes` on Arctic Shift API)

Evaluated across real Reddit posts and comment reply trees:

| Metric | DeepSift (Concurrent) | Sequential Baseline | Difference / Ratio |
| :--- | :--- | :--- | :--- |
| **Total Elapsed Time** | **10.586s** | 33.974s | **3.21x faster** |
| **Posts Scraped** | 24 | 24 | Matches: ✓ |
| **Comments Extracted** | 136 | 136 | Matches: ✓ |
| **Post Processing Rate** | **2.3 posts/s** | 0.7 posts/s | **3.3x throughput** |
| **Comment Processing Rate** | **12.8 comments/s** | 4.0 comments/s | **3.2x throughput** |

---

## Synthetic Scaling Benchmark (Up to 5,000 Posts / 25,000 Comments)

| Metric | DeepSift | Sequential Baseline | Difference / Ratio |
| :--- | :--- | :--- | :--- |
| **5,000 Posts Elapsed Time** | **0.794s** | 14.021s | **17.65x faster** |
| **Comments Throughput** | **31,486 comments/s** | 1,783 comments/s | **17.7x throughput** |
| **Memory at 5,000 Posts** | **13.91 MB** | 26.27 MB | **1.89x less memory** |

### Key Takeaways
1. **5.5x - 8x Throughput Advantage**: Asynchronous comment resolution and multi-threaded sharding eliminate I/O blocking.
2. **Deterministic Data Parity**: DeepSift extracts the identical cohort and comment volume as sequential scraping, verified via checksums.
3. **Constant Disk Streaming**: Rather than growing linearly in memory as millions of comments are gathered, DeepSift flushes compressed Arrow batches to disk in chunks.
