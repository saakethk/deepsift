"""
Resilient, deterministic time-sharded post scraper for Arctic Shift.
Fixes:
- Anchored date boundaries (midnight UTC) so queries are 100% reproducible
- Non-overlapping shard boundaries (strictly exclusive timestamps)
- Exponential backoff (never aborts a shard on temporary network errors)
- Strict in-memory deduplication before writing to Parquet
"""
import sys
from pathlib import Path

# Enable importing sibling modules regardless of how the script is invoked
sys.path.insert(0, str(Path(__file__).resolve().parent))

import os
import time
import requests
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from filters import is_cohort_candidate
from parquet_streamer import ParquetStreamer

# Only request the 9 fields we need
POST_FIELDS = "id,subreddit,title,selftext,url,score,num_comments,link_flair_text,created_utc"


def clean_post(post: dict) -> dict:
    """Normalizes post fields into standard schema."""
    return {
        "id": str(post.get("id")),
        "subreddit": str(post.get("subreddit") or "resumes"),
        "title": str(post.get("title") or ""),
        "selftext": str(post.get("selftext") or ""),
        "url": str(post.get("url") or ""),
        "score": int(post.get("score") or 0),
        "num_comments": int(post.get("num_comments") or 0),
        "flair": str(post.get("link_flair_text") or ""),
        "created_utc": int(post.get("created_utc") or 0),
    }


def generate_anchored_shards(
    days_back: int,
    shard_days: int = 180,
    anchor_dt: datetime = None
) -> list[tuple[int, int]]:
    """
    Generates strictly non-overlapping [start_ts, end_ts] windows.
    Anchors to midnight UTC so repeated runs on the same day produce identical timestamps.
    """
    if anchor_dt is None:
        # Fixed to today's midnight UTC
        now_utc = datetime.now(timezone.utc)
        anchor_dt = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

    shards = []
    current_end = anchor_dt
    target_cutoff = anchor_dt - timedelta(days=days_back)

    while current_end > target_cutoff:
        current_start = max(current_end - timedelta(days=shard_days), target_cutoff)
        
        # Strictly non-overlapping: end timestamp is exclusive (-1 sec on subsequent shards)
        start_ts = int(current_start.timestamp())
        end_ts = int(current_end.timestamp())
        shards.append((start_ts, end_ts))
        
        current_end = current_start - timedelta(seconds=1)

    return shards


def scan_single_shard(
    subreddit: str,
    after_ts: int,
    before_ts: int,
    streamer: ParquetStreamer,
    session: requests.Session,
    seen_ids: set,
    seen_lock
) -> list[str]:
    """
    Scans a single time window backwards with exponential backoff.
    Never aborts early on network errors.
    """
    matched_ids = []
    current_before = before_ts

    while current_before > after_ts:
        url = (
            f"https://arctic-shift.photon-reddit.com/api/posts/search"
            f"?subreddit={subreddit}&limit=100&before={current_before}&after={after_ts}&fields={POST_FIELDS}"
        )

        data = None
        consecutive_errors = 0
        backoff = 2

        # Robust retry loop: up to 5 attempts with exponential backoff
        for attempt in range(5):
            try:
                res = session.get(url, timeout=15)
                if res.status_code == 200:
                    data = res.json().get("data", [])
                    break
                elif res.status_code == 429:
                    time.sleep(backoff)
                    backoff *= 2
                elif res.status_code >= 500:
                    time.sleep(backoff)
                    backoff *= 2
            except requests.RequestException:
                time.sleep(backoff)
                backoff *= 2

        # If server failed after 5 retries, step backward by 1 day rather than aborting shard
        if data is None:
            print(f"\n[!] Network timeout at timestamp {current_before}. Stepping cursor back 1 day...")
            current_before -= 86400
            continue

        # Truly empty list on HTTP 200 -> reached the natural end of this window
        if len(data) == 0:
            break

        matching_batch = []
        for post in data:
            created = int(post.get("created_utc", 0))
            if created <= after_ts:
                break

            post_id = str(post.get("id"))
            with seen_lock:
                if post_id in seen_ids:
                    continue

            if is_cohort_candidate(post):
                cleaned = clean_post(post)
                with seen_lock:
                    if post_id not in seen_ids:
                        seen_ids.add(post_id)
                        matching_batch.append(cleaned)
                        matched_ids.append(cleaned["id"])

        if matching_batch:
            streamer.write_batch(matching_batch)

        oldest_in_batch = data[-1]["created_utc"]
        # Guard against identical-second cursor loops
        if oldest_in_batch >= current_before:
            current_before -= 1
        else:
            current_before = oldest_in_batch

        time.sleep(0.3)  # Polite pacing

    return matched_ids


def collect_cohort_posts(
    subreddit: str = "resumes",
    days_back: int = 5 * 365,
    shard_days: int = 180,
    max_workers: int = 4,
    output_path: str = "data/curated_posts_5yr.parquet",
    anchor_dt: datetime = None
) -> list[str]:
    """
    Deterministic time-sharded parallel post scanning.
    """
    # Remove old output file if starting fresh
    if os.path.exists(output_path):
        os.remove(output_path)

    shards = generate_anchored_shards(days_back, shard_days, anchor_dt)
    print(f"[*] Scanning r/{subreddit} across {len(shards)} non-overlapping time shards ({days_back} days total)...")

    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=12, pool_maxsize=12, max_retries=3)
    session.mount("https://", adapter)

    import threading
    seen_ids = set()
    seen_lock = threading.Lock()
    all_matched_ids = []

    with ParquetStreamer(output_path) as streamer:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    scan_single_shard,
                    subreddit,
                    after_ts,
                    before_ts,
                    streamer,
                    session,
                    seen_ids,
                    seen_lock
                )
                for after_ts, before_ts in shards
            ]

            for future in tqdm(as_completed(futures), total=len(futures), desc="Post Shards"):
                shard_ids = future.result()
                all_matched_ids.extend(shard_ids)

    unique_ids = list(dict.fromkeys(all_matched_ids))
    print(f"[✓] Post scan complete. Saved {len(unique_ids):,} unique cohort posts to {output_path}")
    return unique_ids
