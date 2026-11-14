"""
Generalized Reddit Scraper Library.
Coordinates:
- Multi-subreddit post scanning with time-window sharding
- Explicit from_dt and to_dt datetime windowing
- Pluggable data sources (inheriting from Source ABC)
- Strongly-typed Post and Comment models
- Custom callable Filters and column restriction
- Direct-to-disk streaming to Parquet
"""
import os
import time
import asyncio
import threading
import requests
import httpx
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Union, Optional, Iterable, Tuple
from tqdm import tqdm
from tqdm.asyncio import tqdm as async_tqdm

from scripts.models import Post, Comment
from scripts.filters import Filters
from scripts.sources import Source, ArcticShiftSource
from scripts.storage import ParquetStreamer


def to_utc_datetime(val: Union[datetime, str, None]) -> Optional[datetime]:
    """Normalizes datetime object or ISO/YYYY-MM-DD string to timezone-aware UTC datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)
    if isinstance(val, str):
        v = val.strip()
        try:
            dt = datetime.fromisoformat(v)
        except ValueError:
            dt = datetime.strptime(v, "%Y-%m-%d")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    raise TypeError(f"Expected datetime or str date, got {type(val).__name__}")


class RedditScraper:
    """
    Generalized scraper orchestrator for historical Reddit data.
    Works with any backend conforming to the Source abstract base class.
    """

    def __init__(
        self,
        filters: Optional[Filters] = None,
        source: Optional[Source] = None,
        post_workers: int = 4,
        comment_workers: int = 5,
        shard_days: int = 180,
    ):
        self.filters = filters or Filters()
        self.source = source or ArcticShiftSource()
        self.post_workers = post_workers
        self.comment_workers = comment_workers
        self.shard_days = shard_days

    def _generate_shards(
        self,
        from_dt: Union[datetime, str],
        to_dt: Optional[Union[datetime, str]] = None,
    ) -> Tuple[list[tuple[int, int]], datetime, datetime]:
        """
        Generates non-overlapping time shard windows [start_ts, end_ts].
        Returns: (shards, start_utc, end_utc)
        """
        end = to_utc_datetime(to_dt)
        if end is None:
            now_utc = datetime.now(timezone.utc)
            end = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

        start = to_utc_datetime(from_dt)
        if start is None:
            raise ValueError("from_dt is required")

        if start >= end:
            raise ValueError(f"from_dt ({start}) must be strictly earlier than to_dt ({end})")

        shards = []
        current_end = end

        while current_end > start:
            current_start = max(current_end - timedelta(days=self.shard_days), start)
            shards.append((int(current_start.timestamp()), int(current_end.timestamp())))
            current_end = current_start - timedelta(seconds=1)

        return shards, start, end

    def _scan_shard(
        self, subreddit: str, after_ts: int, before_ts: int,
        streamer: ParquetStreamer, session: requests.Session,
        seen_ids: set, seen_lock: threading.Lock
    ) -> list[str]:
        matched_ids = []

        # Delegate pagination and network querying to data source with minimal field projection
        post_fields = self.filters.required_post_fields
        for batch in self.source.fetch_posts_shard(subreddit, after_ts, before_ts, fields=post_fields, session=session):
            matching_batch = []
            for raw_post in batch:
                if int(raw_post.get("created_utc", 0)) <= after_ts:
                    break

                post_id = str(raw_post.get("id"))
                with seen_lock:
                    if post_id in seen_ids:
                        continue

                # Construct Post object directly from raw payload
                post = Post.from_api_dict(raw_post)

                # Evaluate custom filter with Post object
                if self.filters.is_valid_post(post):
                    with seen_lock:
                        if post_id not in seen_ids:
                            seen_ids.add(post_id)
                            matching_batch.append(self.filters.filter_post_record(post))
                            matched_ids.append(post.id)

            if matching_batch:
                streamer.write_batch(matching_batch)

        return matched_ids

    def scrape_posts(
        self,
        subreddits: Union[str, List[str]],
        from_dt: Union[datetime, str],
        to_dt: Optional[Union[datetime, str]] = None,
        output_path: str = "data/curated_posts.parquet",
    ) -> list[str]:
        """
        Scans one or multiple subreddits across parallel shards between from_dt and to_dt.
        """
        if isinstance(subreddits, str):
            subreddits = [subreddits]

        if os.path.exists(output_path):
            os.remove(output_path)

        shards, start_dt, end_dt = self._generate_shards(from_dt=from_dt, to_dt=to_dt)
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=12, pool_maxsize=12, max_retries=3)
        session.mount("https://", adapter)

        seen_ids = set()
        seen_lock = threading.Lock()
        all_matched_ids = []

        print(
            f"[*] Starting post scan using [{self.source.name}] across {len(subreddits)} subreddit(s)\n"
            f"    Window: {start_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC to {end_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC "
            f"({len(shards)} shards)"
        )

        with ParquetStreamer(output_path) as streamer:
            for sub in subreddits:
                print(f"  --> Scanning r/{sub}...")
                with ThreadPoolExecutor(max_workers=self.post_workers) as executor:
                    futures = [
                        executor.submit(self._scan_shard, sub, after_ts, before_ts, streamer, session, seen_ids, seen_lock)
                        for after_ts, before_ts in shards
                    ]
                    for future in tqdm(as_completed(futures), total=len(futures), desc=f"r/{sub} shards"):
                        all_matched_ids.extend(future.result())

        unique_ids = list(dict.fromkeys(all_matched_ids))
        print(f"[✓] Post scan complete. Saved {len(unique_ids):,} posts to {output_path}")
        return unique_ids

    async def _fetch_comments_for_post(
        self, client: httpx.AsyncClient, post_id: str, semaphore: asyncio.Semaphore,
        fields: Optional[Iterable[str]] = None, max_retries: int = 5
    ) -> tuple[str, list[dict], bool]:
        async with semaphore:
            clean_id, raw_comments, success = await self.source.fetch_comments_for_post(
                client=client, post_id=post_id, fields=fields, max_retries=max_retries
            )

        # Filter raw comments through filters and select columns
        filtered_comments = []
        for raw_c in raw_comments:
            comment = Comment.from_api_dict(raw_c, clean_id)
            if self.filters.is_valid_comment(comment):
                filtered_comments.append(self.filters.filter_comment_record(comment))

        return clean_id, filtered_comments, success

    async def _scrape_comments_async(self, post_ids: list[str], output_path: str, chunk_size: int = 500) -> int:
        if os.path.exists(output_path):
            os.remove(output_path)

        limits = httpx.Limits(max_keepalive_connections=20, max_connections=20)
        semaphore = asyncio.Semaphore(self.comment_workers)
        total_saved, buffer, failed_posts = 0, [], []

        print(f"[*] Fetching comments using [{self.source.name}] for {len(post_ids):,} posts with {self.comment_workers} async workers...")

        comment_fields = self.filters.required_comment_fields
        with ParquetStreamer(output_path) as streamer:
            async with httpx.AsyncClient(limits=limits) as client:
                tasks = [self._fetch_comments_for_post(client, pid, semaphore, fields=comment_fields) for pid in post_ids]

                for future in async_tqdm.as_completed(tasks, total=len(tasks), desc="Comments"):
                    post_id, comments, success = await future
                    if not success:
                        failed_posts.append(post_id)
                    if comments:
                        buffer.extend(comments)

                    if len(buffer) >= chunk_size:
                        streamer.write_batch(buffer)
                        total_saved += len(buffer)
                        buffer = []

                if failed_posts:
                    print(f"\n[*] Retrying {len(failed_posts)} failed posts...")
                    await asyncio.sleep(2.0)
                    retry_tasks = [
                        self._fetch_comments_for_post(client, pid, semaphore, fields=comment_fields, max_retries=6)
                        for pid in failed_posts
                    ]
                    for future in async_tqdm.as_completed(retry_tasks, total=len(retry_tasks), desc="Retries"):
                        _, comments, _ = await future
                        if comments:
                            buffer.extend(comments)

                if buffer:
                    streamer.write_batch(buffer)
                    total_saved += len(buffer)

        print(f"[✓] Comments complete. Saved {total_saved:,} comments to {output_path}")
        return total_saved

    def scrape_comments(
        self,
        post_ids: list[str],
        output_path: str = "data/curated_comments.parquet",
        chunk_size: int = 500,
    ) -> int:
        """
        Concurrently scrapes comments for target posts and writes to Parquet.
        """
        if not post_ids:
            print("[!] No post IDs provided for comment scraping.")
            return 0

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(self._scrape_comments_async(post_ids, output_path, chunk_size))
        return asyncio.run(self._scrape_comments_async(post_ids, output_path, chunk_size))

    def run(
        self,
        subreddits: Union[str, List[str]],
        from_dt: Union[datetime, str],
        to_dt: Optional[Union[datetime, str]] = None,
        posts_output: str = "data/curated_posts.parquet",
        comments_output: str = "data/curated_comments.parquet",
    ) -> tuple[list[str], int]:
        """
        Runs full pipeline: post scanning -> filtering -> comment extraction.
        Requires explicit from_dt and optional to_dt.
        """
        matched_post_ids = self.scrape_posts(
            subreddits=subreddits,
            from_dt=from_dt,
            to_dt=to_dt,
            output_path=posts_output,
        )

        total_comments = 0
        if matched_post_ids:
            total_comments = self.scrape_comments(
                post_ids=matched_post_ids,
                output_path=comments_output,
            )

        return matched_post_ids, total_comments
