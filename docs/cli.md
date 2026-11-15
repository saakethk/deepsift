# Command Line Interface (CLI)

DeepSift provides command-line utilities via the `deepsift` and `reddit-scraper` binaries.

---

## 1. `deepsift run` (Full Pipeline)

Runs the complete extraction workflow: post scraping, cohort filtering, and comment tree traversal.

```bash
deepsift run \
  --subreddits resumes \
  --from 2024-01-01 \
  --to 2024-01-15 \
  --shard-days 7 \
  --include-fields id \
  --include-fields title \
  --include-fields score \
  --include-fields num_comments \
  --include-fields created_utc \
  --post-workers 4 \
  --comment-workers 5 \
  --posts-out data/posts.parquet \
  --comments-out data/comments.parquet
```

### Options Reference

| Option | Flag | Default | Description |
| :--- | :--- | :--- | :--- |
| `--subreddits` | `-s` | `['resumes']` | Subreddit(s) to scan. May be specified multiple times. |
| `--from` | | *Required* | Start date or timestamp (YYYY-MM-DD or ISO 8601). |
| `--to` | | `None` (now) | End date or timestamp. |
| `--shard-days` | | `180` | Window size in days per worker shard. |
| `--include-fields` | `-i` | `None` | Important post fields to request (validated against PostField enum). |
| `--exclude-fields` | `-e` | `None` | Unneeded post fields to drop from wire request. |
| `--comment-include-fields` | | `None` | Comment fields to keep. |
| `--comment-exclude-fields` | | `None` | Comment fields to drop. |
| `--posts-out` | | `data/curated_posts.parquet` | Parquet output path for posts. |
| `--comments-out` | | `data/curated_comments.parquet` | Parquet output path for comments. |
| `--errors-out` | | `data/errors.json` | JSON output destination for failure logs. |
| `--post-workers` | | `4` | Number of parallel shard post workers. |
| `--comment-workers` | | `5` | Async comment concurrency workers. |

---

## 2. `deepsift posts` (Posts Only)

Scrapes only submissions for the target subreddits:

```bash
deepsift posts \
  --subreddits resumes \
  --from 2024-01-01 \
  --to 2024-01-10 \
  --shard-days 1 \
  --post-workers 4 \
  --output data/posts.parquet
```

---

## 3. `deepsift comments` (Comments Only)

Extracts comment trees for specific Reddit submission IDs:

```bash
deepsift comments \
  --post-id 18w1xyz \
  --post-id 18w2abc \
  --workers 5 \
  --output data/comments.parquet
```
