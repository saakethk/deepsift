# Quickstart Guide

This guide covers common usage patterns for DeepSift in Python.

---

## 1. Scrape Filtered Submissions

To scrape posts with selective field projection and custom predicate filtering:

```python
from deepsift.scraper import RedditScraper
from deepsift.filters import Filters
from deepsift.models import PostField

# Request only the fields your analysis needs over the wire
filters = Filters(
    post_include_fields=[
        PostField.ID,
        PostField.TITLE,
        PostField.SCORE,
        PostField.NUM_COMMENTS,
        PostField.CREATED_UTC,
        PostField.SUBREDDIT,
    ],
    post_filter=lambda post: post.score >= 5 and post.num_comments >= 3,
)

scraper = RedditScraper(
    filters=filters,
    post_workers=4,
    shard_days=30,
)

post_ids = scraper.scrape_posts(
    subreddits=["resumes"],
    from_dt="2024-01-01",
    to_dt="2024-02-01",
    output_path="data/curated_posts.parquet",
)

print(f"Scraped {len(post_ids)} curated posts.")
```

---

## 2. Complete Ingestion Pipeline (Posts + Comment Trees)

To scrape both submissions and their entire discussion trees concurrently:

```python
from deepsift.scraper import RedditScraper
from deepsift.filters import Filters

filters = Filters(
    post_filter=lambda p: p.score > 0,
    comment_filter=lambda c: len(c.body or "") >= 20,
)

scraper = RedditScraper(
    filters=filters,
    post_workers=4,
    comment_workers=5,
    shard_days=7,
)

posts, comment_count = scraper.run(
    subreddits=["resumes"],
    from_dt="2024-01-01",
    to_dt="2024-01-08",
    posts_output="data/posts.parquet",
    comments_output="data/comments.parquet",
    errors_output="data/errors.json",
)

print(f"Ingested {len(posts)} posts and {comment_count} comments.")
```

---

## 3. Offline Synthetic Testing with DummySource

To test your analysis pipelines or run benchmarks offline without hitting external networks:

```python
from deepsift.scraper import RedditScraper
from deepsift.sources.dummy import DummySource

# Generates randomized, realistic posts and comments locally
dummy = DummySource(
    posts_per_shard=100,
    comments_per_post=5,
    simulated_latency=0.25, # 250ms simulated network latency
)

scraper = RedditScraper(
    source=dummy,
    post_workers=2,
    shard_days=1,
)

post_ids = scraper.scrape_posts(
    subreddits=["resumes"],
    from_dt="2024-01-01",
    to_dt="2024-01-05",
    output_path="data/dummy_posts.parquet",
)
```
