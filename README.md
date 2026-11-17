# DeepSift

[![PyPI version](https://img.shields.io/pypi/v/deepsift.svg)](https://pypi.org/project/deepsift/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

DeepSift is a high-performance Python library designed for empirical and academic researchers to scrape, filter, and curate massive historical Reddit datasets at scale.

By combining **parallel temporal sharding**, **server-side field projection**, and **PyArrow Parquet streaming**, DeepSift overcomes the common bottlenecks of Reddit data collection—slashing bandwidth, keeping memory footprint constant, and achieving over **4.5x faster throughput** than standard sequential scrapers.

---

## Key Performance Advantages

* **Multi-Worker Temporal Sharding**: Splits arbitrary multi-month or multi-year windows into discrete temporal segments across parallel thread workers with adaptive backoff and rate-limit recovery.
* **Server-Side Field Projection**: Mathematically projects predicates to request only the attributes needed by your downstream study over the wire, cutting payload bandwidth by up to **24.0x**.
* **Constant-Memory Parquet Streaming**: Flushes chunked batches straight to columnar Apache Parquet files via PyArrow, reducing peak RAM consumption by up to **16.8x** compared to in-memory buffering.
* **Asynchronous Comment Tree Resolution**: Extracts and flattens deeply nested discussion trees using `httpx` async workers with configurable concurrency limits and automatic `"more"` stub pruning.
* **Polymorphic Schema Coercion**: Handles schema anomalies (such as polymorphic `edited` timestamps, flairs, and variable-typed metadata) without failing batch serialization.

---

## Installation

Install the library directly from PyPI:

```bash
pip install deepsift
```

To install local development dependencies:
```bash
pip install deepsift[dev]
```

---

## Quickstart

### 1. Python API

```python
import pandas as pd
from deepsift import RedditScraper, Filters, PostField, CommentField

# Request only the fields needed for your analysis
filters = Filters(
    post_include_fields=[
        PostField.ID,
        PostField.TITLE,
        PostField.SELFTEXT,
        PostField.SCORE,
        PostField.NUM_COMMENTS,
        PostField.AUTHOR,
        PostField.CREATED_UTC,
        PostField.SUBREDDIT,
    ],
    comment_include_fields=[
        CommentField.ID,
        CommentField.POST_ID,
        CommentField.PARENT_ID,
        CommentField.AUTHOR,
        CommentField.BODY,
        CommentField.SCORE,
        CommentField.CREATED_UTC,
    ],
    post_filter=lambda p: (p.score or 0) >= 3 and (p.num_comments or 0) >= 1,
    comment_filter=lambda c: len(c.body or "") >= 20 and c.author != "[deleted]",
)

# Configure parallel workers and temporal shard granularity
scraper = RedditScraper(
    filters=filters,
    post_workers=4,
    comment_workers=5,
    shard_days=7,
)

# Run full ingestion pipeline (submissions + comment trees)
post_ids, comment_count = scraper.run(
    subreddits=["MachineLearning"],
    from_dt="2024-01-01",
    to_dt="2024-01-14",
    posts_output="data/posts.parquet",
    comments_output="data/comments.parquet",
    errors_output="data/errors.json",
)

print(f"Scraped {len(post_ids)} posts and {comment_count} comments.")

# Open directly into pandas, Polars, or DuckDB
df_posts = pd.read_parquet("data/posts.parquet")
df_comments = pd.read_parquet("data/comments.parquet")
```

### 2. Command Line Interface (CLI)

DeepSift includes a CLI for pipeline execution and quick queries:

```bash
# Run complete post + comment pipeline
deepsift run --subreddit MachineLearning --from 2024-01-01 --to 2024-01-07 --posts data/posts.parquet --comments data/comments.parquet

# Scrape posts only
deepsift posts --subreddit resumes --from 2024-01-01 --to 2024-01-30 --output data/resumes_posts.parquet

# Extract comments for specific post IDs
deepsift comments --post-ids id1,id2,id3 --output data/extracted_comments.parquet
```

### 3. Offline Testing with `DummySource`

For unit testing, benchmarking, or development without network calls, swap in `DummySource` to generate realistic synthetic posts and comments:

```python
from deepsift import RedditScraper, Filters
from deepsift.sources.dummy import DummySource

dummy = DummySource(posts_per_shard=100, comments_per_post=5, simulated_latency=0.0)
scraper = RedditScraper(source=dummy, shard_days=1)
```

---

## Evaluation & Benchmarks

Empirical performance evaluation comparing DeepSift (6 parallel workers) against standard sequential extraction:

| Benchmark Scenario | Cohort Scale | DeepSift (6w) | Sequential (1w) | Speedup | Ingestion Dynamics | Resource Advantage |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Live API Ingestion** | 930 Posts (10 Days, `r/resumes`) | **3.58 ± 1.29s** | 14.91 ± 2.46s | **4.16x** | **799ms** avg API latency | **24.0x less bandwidth**, **16.8x less RAM** |
| **Synthetic Scaling** | 1,000 Posts (`DummySource`) | **0.56 ± 0.01s** | 2.58 ± 0.00s | **4.59x** | **250ms** simulated latency | **1.4x less RAM** (streaming Parquet) |

To reproduce the benchmark suite:
```bash
python -m evaluation
```

---

## Running Tests

Run the test suite offline using synthetic data:
```bash
pytest -m "not live" -v
```

Run live integration tests against real historical endpoints:
```bash
pytest -m live -v
```

---

## Documentation

The full documentation website is built with [Astro Starlight](https://starlight.astro.build/) and is located in the [`docs/`](docs/) directory.

To start the documentation dev server locally:
```bash
cd docs
npm install
npm run dev
```
Then visit `http://localhost:4321/` in your browser.

Documentation sources:
* [Overview & Architecture](docs/src/content/docs/architecture.md)
* [Quickstart Guide](docs/src/content/docs/quickstart.md)
* [Python API Reference](docs/src/content/docs/api.md)
* [CLI Reference](docs/src/content/docs/cli.md)
* [Benchmarks & Scaling](docs/src/content/docs/benchmarks.md)

---

## License

This project is licensed under the [MIT License](LICENSE).
