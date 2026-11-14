"""
Generalized Reddit Scraper Library.
Coordinates:
- Multi-subreddit post scanning with time-window sharding
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
from typing import List, Union, Optional
from tqdm import tqdm
from tqdm.asyncio import tqdm as async_tqdm

from scripts.models import Post, Comment
from scripts.filters import Filters
from scripts.sources import Source, ArcticShiftSource
from scripts.parquet_streamer import ParquetStreamer


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

    # -------------------------------------------------------------------------
    # POSTS SCRAPING
    # -------------------------------------------------------------------------
    def _generate_shards(self, days_back: int, anchor_dt: Optional[datetime] = None) -> list[tuple[int, int]]:
        if anchor_dt is None:
            now_utc = datetime.now(timezone.utc)
            anchor_dt = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

        shards = []
        current_end = anchor_dt
        target_cutoff = anchor_dt - timedelta(days=days_back)

        while current_end > target_cutoff:
            current_start = max(current_end - timedelta(days=self.shard_days), target_cutoff)
            shards.append((int(current_start.timestamp()), int(current_end.timestamp())))
            current_end = current_start - timedelta(seconds=1)

        return shards

    def _scan_shard(
        self, subreddit: str, after_ts: int, before_ts: int,
        streamer: ParquetStreamer, session: requests.Session,
        seen_ids: set, seen_lock: threading.Lock
    ) -> list[str]:
        matched_ids = []

        # Delegate pagination and network querying to data source
        for batch in self.source.fetch_posts_shard(subreddit, after_ts, before_ts, session=session):
            matching_batch = []
            for raw_post in batch:
                if int(raw_post.get("created_utc", 0)) <= after_ts:
                    break

                post_id = str(raw_post.get("id"))
                with seen_lock:
                    if post_id in seen_ids:
                        continue

                # Validate against known API fields and construct Post object
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
        subreddits: Union[str, List[str]] = "resumes",
        days_back: int = 5 * 365,
        output_path: str = "data/curated_posts_5yr.parquet",
        anchor_dt: Optional[datetime] = None,
    ) -> list[str]:
        """
        Scans one or multiple subreddits across parallel shards and writes matching posts to Parquet.
        """
        if isinstance(subreddits, str):
            subreddits = [subreddits]

        if os.path.exists(output_path):
            os.remove(output_path)

        shards = self._generate_shards(days_back, anchor_dt)
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=12, pool_maxsize=12, max_retries=3)
        session.mount("https://", adapter)

        seen_ids = set()
        seen_lock = threading.Lock()
        all_matched_ids = []

        print(f"[*] Starting post scan using [{self.source.name}] across {len(subreddits)} subreddit(s) and {len(shards)} shard(s)...")

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

    # -------------------------------------------------------------------------
    # COMMENTS SCRAPING
    # -------------------------------------------------------------------------
    async def _fetch_comments_for_post(
        self, client: httpx.AsyncClient, post_id: str, semaphore: asyncio.Semaphore, max_retries: int = 5
    ) -> tuple[str, list[dict], bool]:
        async with semaphore:
            clean_id, raw_comments, success = await self.source.fetch_comments_for_post(
                client=client, post_id=post_id, max_retries=max_retries
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

        with ParquetStreamer(output_path) as streamer:
            async with httpx.AsyncClient(limits=limits) as client:
                tasks = [self._fetch_comments_for_post(client, pid, semaphore) for pid in post_ids]

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
                    retry_tasks = [self._fetch_comments_for_post(client, pid, semaphore, max_retries=6) for pid in failed_posts]
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
        output_path: str = "data/curated_comments_5yr.parquet",
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

    # -------------------------------------------------------------------------
    # UNIFIED PIPELINE RUNNER
    # -------------------------------------------------------------------------
    def run(
        self,
        subreddits: Union[str, List[str]] = "resumes",
        days_back: int = 5 * 365,
        posts_output: str = "data/curated_posts_5yr.parquet",
        comments_output: str = "data/curated_comments_5yr.parquet",
        anchor_dt: Optional[datetime] = None,
    ) -> tuple[list[str], int]:
        """
        Runs full pipeline: post scanning -> filtering -> comment extraction.
        """
        matched_post_ids = self.scrape_posts(
            subreddits=subreddits,
            days_back=days_back,
            output_path=posts_output,
            anchor_dt=anchor_dt,
        )

        total_comments = 0
        if matched_post_ids:
            total_comments = self.scrape_comments(
                post_ids=matched_post_ids,
                output_path=comments_output,
            )

        return matched_post_ids, total_comments
