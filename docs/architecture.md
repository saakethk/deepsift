# Architecture & Ingestion Pipeline

DeepSift coordinates data ingestion through decoupled, concurrent stages:

```
┌─────────────────────────────────────────────────────────────┐
│                        RedditScraper                        │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
               ▼                               ▼
    ┌──────────────────────┐        ┌──────────────────────┐
    │  Post Shard Workers  │        │ Async Comment Pool   │
    │  (ThreadPoolExecutor)│        │ (httpx.AsyncClient)  │
    └──────────┬───────────┘        └──────────┬───────────┘
               │                               │
               ▼                               ▼
    ┌──────────────────────┐        ┌──────────────────────┐
    │        Source        │        │        Source        │
    │  (ArcticShiftSource  │        │  (ArcticShiftSource  │
    │   or DummySource)    │        │   or DummySource)    │
    └──────────┬───────────┘        └──────────┬───────────┘
               │                               │
               ▼                               ▼
    ┌──────────────────────┐        ┌──────────────────────┐
    │       Filters        │        │       Filters        │
    │ (Predicate + Proj.)  │        │ (Predicate + Proj.)  │
    └──────────┬───────────┘        └──────────┬───────────┘
               │                               │
               ▼                               ▼
    ┌─────────────────────────────────────────────────────────┐
    │                     ParquetStorage                      │
    │          (Thread-Safe PyArrow Chunked Writer)           │
    └─────────────────────────────────────────────────────────┘
```

---

## 1. Temporal Window Sharding

Given a multi-month or multi-year query window `[from_dt, to_dt]`, DeepSift automatically calculates non-overlapping shards based on `shard_days`:

- Each shard worker receives a temporal slice (e.g. 30 days or 180 days).
- Workers query the source concurrently, paginating until the slice boundary is reached.
- Parallelism scales across multiple thread workers (`post_workers=4`, `post_workers=6`).

---

## 2. Server-Side Field Projection Minimization

Reddit submissions and comments contain over 100 attributes, many of which (such as rich text flair payloads, media metadata, and award icons) are large and unneeded for text or metadata research.

DeepSift calculates minimal projections:
- If `include_fields` is specified: requests `include_fields ∪ REQUIRED_FIELDS`.
- If `exclude_fields` is specified: requests `ALL_KNOWN_FIELDS \ exclude_fields ∪ REQUIRED_FIELDS`.
- Core schema identifiers (`id`, `created_utc`, `subreddit`) are protected from exclusion.

This reduces the average post record size from **~3.1 KB** down to **~130 bytes**, cutting bandwidth by **24x**.

---

## 3. Streaming Parquet Storage & Schema Coercion

Traditional approaches collect lists of dictionaries in memory and convert them to a pandas DataFrame at the end of the scrape. This leads to out-of-memory errors on large cohorts.

DeepSift streams batches straight to disk via `ParquetStorage`:
- **Thread-Safe**: Multiple workers stream into the same Parquet file concurrently under a reentrant lock.
- **Polymorphic Coercion**: Fields such as `edited` (which Reddit returns as either a boolean `false` or an integer Unix timestamp) are normalized to uniform string columns to prevent schema conflicts.
- **Constant Memory Footprint**: Tracemalloc profiling confirms RAM usage stays under 20 MB regardless of dataset size.
