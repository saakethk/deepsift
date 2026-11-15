# Resume Model-V3
What constitutes an 'effective' resume remains largely subjective and governed by anecdotal heuristics rather than empirical evidence. Furthermore, strict privacy regulations (e.g., GDPR, PII compliance) and corporate liability prevent real-world applicant tracking datasets from being made public. To overcome this data bottleneck, this study leverages crowdsourced data from major resume-focused Reddit communities to empirically analyze community feedback, isolate recurring structural defects, and quantify the presentation features that drive resume efficacy.

## Methodology
To perform this analysis, we first wanted to identify the largest relevant subreddits related to our topic of resumes. Utilizing the [PRAW](https://praw.readthedocs.io/en/stable/), we pulled the top 100 subreddits for the search term "resume" ([code](find_relevant_posts.ipynb), [data](data/subs_df_snapshot_11_11_2026.csv)).

We found that 47% of the subreddits contained the relevant search term "resume" (ignoring case). This cohort was then refined further to include communities of a significant size (median subscriber count >= **1091**). The cohort of relevant subreddits (n=23) we decided to investigate can be seen below:

[![Graph of subscribers per relevant subreddit](data/graph_relevant_subreddits_fig_11_11_26.png)](data/relevant_subs_cohort_11_11_2026.csv)

We then got **10,183** posts in the largest relevant subreddit (r/resumes) dating back to May 14, 2026. This was our preliminary cohort consisting of 180 days of data ([code](explore_relevant_posts.ipynb), [data](data/prelim_historical_10000_11_11_26.csv)) which we intended to perform preliminary exploratory data analysis (EDA) on to determine which posts we need to focus on for our larger planned cohort consisting of 5 years of data (1825 days).

We determined that the ideal cohort for our use case needed to satisfy the following factors:
- have >10 comments and >0 score
- have a associated url corresponding to a picture (.png or jpeg)

After evaluating the preliminary cohort of data against these standards, we found that **115** of the posts satisfied the conditions ([code](explore_relevant_posts.ipynb), [data](data/subs_df_snapshot_11_11_2026.csv)). We took these 115 and analyzed them further to determine if their comments provided relevant feedback.



# Testing
To run the static unit and integration test suite offline using the synthetic `DummySource`:
```bash
pytest -m "not live" -v
```

To run the live integration tests against the actual Arctic Shift API:
```bash
pytest -m live -v
```

# Evaluation & Benchmarks
Comprehensive performance evaluations comparing DeepSift against sequential execution:

| Benchmark Scenario | Cohort Scale | DeepSift (6w) | Sequential (1w) | Speedup | Ingestion Dynamics | Resource Advantage |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Live API Ingestion** | 930 Posts (10 Days, `r/resumes`) | **3.58 ± 1.29s** | 14.91 ± 2.46s | **4.16x** | **799ms** avg API latency | **24.0x less bandwidth**, **16.8x less RAM** |
| **Synthetic Scaling** | 1,000 Posts (`DummySource`) | **0.56 ± 0.01s** | 2.58 ± 0.00s | **4.59x** | **250ms** simulated latency | **1.4x less RAM** (streaming Parquet) |

To run the evaluations:
```bash
# Unified scaling benchmark (runs both Live API and Synthetic Dummy together)
python -m evaluation
```

# Documentation Site
The documentation site is powered by [MkDocs](https://www.mkdocs.org/) with the [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) theme.

To serve the documentation locally with hot-reloading:
```bash
mkdocs serve
```
Then visit `http://127.0.0.1:8000` in your browser.

To build the static HTML site (generated into `site/`):
```bash
mkdocs build
```
You can view the pre-built site directly: [site/index.html](file:///Users/saakethkesireddy/Desktop/job_journal/resume_model/site/index.html).

Documentation sources are structured under [docs/](file:///Users/saakethkesireddy/Desktop/job_journal/resume_model/docs/):
- [Overview & Architecture](file:///Users/saakethkesireddy/Desktop/job_journal/resume_model/docs/architecture.md)
- [Quickstart Guide](file:///Users/saakethkesireddy/Desktop/job_journal/resume_model/docs/quickstart.md)
- [Python API Reference](file:///Users/saakethkesireddy/Desktop/job_journal/resume_model/docs/api.md)
- [CLI Reference](file:///Users/saakethkesireddy/Desktop/job_journal/resume_model/docs/cli.md)
- [Benchmarks & Performance](file:///Users/saakethkesireddy/Desktop/job_journal/resume_model/docs/benchmarks.md)

# TODO
- [x] make static tests using dummy source (runs on github ci/cd)
- [x] make live tests using actual source on r/resumes
- [x] make evaluation script
- [x] writeup and documentation with benchmarks, docs page, and cleaned repo