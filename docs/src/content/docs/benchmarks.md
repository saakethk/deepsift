---
title: Performance & Benchmarks
description: Benchmarking DeepSift against sequential scrapers across throughput, memory, and bandwidth.
---

DeepSift includes a benchmarking harness (`evaluation`) measuring throughput, latency, memory consumption, and concurrency speedup compared to naive sequential scrapers.

---

## Benchmark Comparison Table

| Metric | DeepSift (6 Workers) | Naive Sequential (1 Worker) | Speedup / Advantage |
| :--- | :--- | :--- | :--- |
| **Live API Ingestion (10 Days, r/resumes)** | **3.58 ± 1.29s** | 14.91 ± 2.46s | **4.16x faster** |
| **Synthetic Scaling (1,000 Posts)** | **0.56 ± 0.01s** | 2.58 ± 0.00s | **4.59x faster** |
| **Wire Bandwidth (Server Projection)** | **120 KB** | 2,880 KB | **24.0x less data** |
| **Peak RAM Consumption** | **18.4 MB** | 309.1 MB | **16.8x less RAM** |

---

## Running the Unified Benchmark Suite

The unified benchmark executes both Live API scaling and Synthetic scaling together, saving summary tables, trial logs, and grouped bar charts into a timestamped directory under `evaluation/results/`:

```bash
# Unified benchmark running Live API and Synthetic Dummy evaluations
python -m evaluation
```

### Options

```bash
# Run 5 trials per window
python -m evaluation --trials 5

# Benchmark a custom subreddit
python -m evaluation --subreddit cscareerquestions

# Run only synthetic scaling
python -m evaluation --mode dummy

# Run only live scaling
python -m evaluation --mode live
```
