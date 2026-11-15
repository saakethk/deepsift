# DeepSift: High-Performance Reddit Data Engine

DeepSift is a production-grade Python library and CLI designed for large-scale, historical Reddit data extraction and research. It interfaces with historical Reddit archives (such as [Arctic Shift](https://arctic-shift.photon-reddit.com/)) and custom data providers to ingest, filter, and stream massive datasets with high throughput, minimal memory overhead, and minimal network bandwidth.

---

## Key Highlights

- **4.6x Higher Throughput**: Parallel temporal sharding (`post_workers`) with adaptive date segmentation.
- **24x Less Wire Bandwidth**: Server-side field projection requests only the exact attributes required by your predicates.
- **16.8x Lower Peak RAM**: Streams chunked batches straight to Apache Parquet via PyArrow without unbounded memory buffering.
- **Asynchronous Comment Tree Traversal**: Fetches complete discussion trees concurrently using `httpx` HTTP/2 clients (`comment_workers`).
- **Polymorphic Schema Normalization**: Seamlessly coerces variable-type Reddit attributes (e.g., `edited`, link flairs, distinguished statuses) to prevent cross-batch schema conflicts.
- **Type Safety & Typo Hints**: Features 100+ strongly-typed post and comment fields with fuzzy string matching suggestions.

---

## Documentation Guide

- [Architecture & Pipeline](architecture.md): Visual data flow, temporal sharding mechanics, and server-side projection math.
- [Quickstart Guide](quickstart.md): Python code examples for submission scraping, full pipelines, and offline mock testing.
- [API Reference](api.md): Detailed reference for `RedditScraper`, `Filters`, models, sources, and `ParquetStorage`.
- [CLI Reference](cli.md): Command-line options for `deepsift run`, `deepsift posts`, and `deepsift comments`.
- [Benchmarks & Performance](benchmarks.md): Comprehensive scaling benchmarks, speedup curves, and evaluation harness.

---

## Installation

DeepSift requires Python 3.11+.

```bash
# Clone the repository
git clone https://github.com/saakethk/resume_model.git
cd resume_model

# Install in editable mode with development dependencies
pip install -e ".[dev,docs]"
```

Verify your installation:

```bash
deepsift --help
```

