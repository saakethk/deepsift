"""
Resilient, deterministic time-sharded post scraper for Arctic Shift.
Features:
- Anchored date boundaries (midnight UTC) for 100% reproducible queries
- Non-overlapping shard boundaries (strictly exclusive timestamps)
- Exponential backoff for network resilience
- Strict in-memory deduplication before writing to Parquet
"""
import os
import time
import threading
import requests
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from scripts.filters import is_cohort_post
from scripts.parsers import clean_post
from scripts.parquet_streamer import ParquetStreamer

POST_FIELDS = "id,subreddit,title,selftext,url,score,num_comments,link_flair_text,created_utc"


def generate_anchored_shards(days_back: int, shard_days: int = 180, anchor_dt: datetime = None) -> list[tuple[int, int]]:
    """Generates non-overlapping [start_ts, end_ts] windows anchored to midnight UTC."""
    if anchor_dt is None:
        now_utc = datetime.now(timezone.utc)
        anchor_dt = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

    shards = []
    current_end = anchor_dt
    target_cutoff = anchor_dt - timedelta(days=days_back)

    while current_end > target_cutoff:
        current_start = max(current_end - timedelta(days=shard_days), target_cutoff)
        shards.append((int(current_start.timestamp()), int(current_end.timestamp())))
        current_end = current_start - timedelta(seconds=1)

    return shards


def scan_single_shard(
    subreddit: str, after_ts: int, before_ts: int, streamer: ParquetStreamer,
    session: requests.Session, seen_ids: set, seen_lock: threading.Lock
) -> list[str]:
    """Scans a single time window backwards with exponential backoff and deduplication."""
    matched_ids = []
    current_before = before_ts

    while current_before > after_ts:
        url = (
            f"https://arctic-shift.photon-reddit.com/api/posts/search"
            f"?subreddit={subreddit}&limit=100&before={current_before}&after={after_ts}&fields={POST_FIELDS}"
        )

        data = None
        backoff = 2.0
        for _ in range(5):
            try:
                res = session.get(url, timeout=15)
                if res.status_code == 200:
                    data = res.json().get("data", [])
                    break
                time.sleep(backoff)
                backoff *= 1.8
            except requests.RequestException:
                time.sleep(backoff)
                backoff *= 1.8

        if data is None:
            current_before -= 86400  # Step back 1 day on persistent error
            continue

        if not data:
            break

        matching_batch = []
        for post in data:
            if int(post.get("created_utc", 0)) <= after_ts:
                break

            post_id = str(post.get("id"))
            with seen_lock:
                if post_id in seen_ids:
                    continue

            if is_cohort_post(post):
                cleaned = clean_post(post)
                with seen_lock:
                    if post_id not in seen_ids:
                        seen_ids.add(post_id)
                        matching_batch.append(cleaned)
                        matched_ids.append(cleaned["id"])

        if matching_batch:
            streamer.write_batch(matching_batch)

        oldest = data[-1]["created_utc"]
        current_before = current_before - 1 if oldest >= current_before else oldest
        time.sleep(0.3)

    return matched_ids


def collect_cohort_posts(
    subreddit: str = "resumes", days_back: int = 5 * 365, shard_days: int = 180,
    max_workers: int = 4, output_path: str = "data/curated_posts_5yr.parquet", anchor_dt: datetime = None
) -> list[str]:
    """Scans historical posts in parallel time shards and saves matching candidates to Parquet."""
    if os.path.exists(output_path):
        os.remove(output_path)

    shards = generate_anchored_shards(days_back, shard_days, anchor_dt)
    print(f"[*] Scanning r/{subreddit} across {len(shards)} shards ({days_back} days total)...")

    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=12, pool_maxsize=12, max_retries=3)
    session.mount("https://", adapter)

    seen_ids = set()
    seen_lock = threading.Lock()
    all_matched_ids = []

    with ParquetStreamer(output_path) as streamer:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(scan_single_shard, subreddit, after_ts, before_ts, streamer, session, seen_ids, seen_lock)
                for after_ts, before_ts in shards
            ]
            for future in tqdm(as_completed(futures), total=len(futures), desc="Post Shards"):
                all_matched_ids.extend(future.result())

    unique_ids = list(dict.fromkeys(all_matched_ids))
    print(f"[✓] Saved {len(unique_ids):,} unique cohort posts to {output_path}")
    return unique_ids
