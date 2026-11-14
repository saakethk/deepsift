"""
Generalized Reddit Scraper Library.
Coordinates parallel shard post scanning and async comment extraction.
"""
import os
import asyncio
import threading
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Union, Optional, Tuple, Type
import requests
import httpx
from tqdm import tqdm
from tqdm.asyncio import tqdm as async_tqdm

from scripts.models import Post, Comment
from scripts.filters import Filters
from scripts.sources import Source, ArcticShiftSource
from scripts.storage import Storage, ParquetStorage


def to_utc_datetime(val: Union[datetime, str, int, float, None]) -> Optional[datetime]:
    """Normalizes input to timezone-aware UTC datetime."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val, tz=timezone.utc)
    if isinstance(val, datetime):
        return val.astimezone(timezone.utc) if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if isinstance(val, str):
        v = val.strip().replace("Z", "+00:00")
        try:
            val = datetime.fromisoformat(v)
        except ValueError:
            val = datetime.strptime(v, "%Y-%m-%d")
        return val.astimezone(timezone.utc) if val.tzinfo else val.replace(tzinfo=timezone.utc)
    raise TypeError(f"Expected datetime, numeric timestamp, or str date, got {type(val).__name__}")


class RedditScraper:
    """Generalized orchestrator for historical Reddit data collection."""

    def __init__(
        self,
        filters: Optional[Filters] = None,
        source: Optional[Source] = None,
        storage_cls: Type[Storage] = ParquetStorage,
        post_workers: int = 4,
        comment_workers: int = 5,
        shard_days: int = 180,
    ):
        self.filters = filters or Filters()
        self.source = source or ArcticShiftSource()
        self.storage_cls = storage_cls
        self.post_workers = post_workers
        self.comment_workers = comment_workers
        self.shard_days = shard_days

    def _generate_shards(self, from_dt: Union[datetime, str], to_dt: Optional[Union[datetime, str]]) -> Tuple[list, datetime, datetime]:
        end = to_utc_datetime(to_dt) or datetime.now(timezone.utc)
        start = to_utc_datetime(from_dt)
        if not start or start >= end:
            raise ValueError(f"Invalid range: from_dt ({start}) must precede to_dt ({end})")

        shards, cur = [], end
        while cur > start:
            prev = max(cur - timedelta(days=self.shard_days), start)
            shards.append((int(prev.timestamp()), int(cur.timestamp())))
            cur = prev
        return shards, start, end

    def _scan_shard(self, subreddit: str, after_ts: int, before_ts: int, streamer: Storage, seen: set, lock: threading.Lock) -> list[str]:
        matched = []
        reached_end = False
        with requests.Session() as session:
            for batch in self.source.fetch_posts_shard(subreddit, after_ts, before_ts, fields=self.filters.required_post_fields, session=session):
                rows = []
                for raw in batch:
                    if int(raw.get("created_utc", 0)) < after_ts:
                        reached_end = True
                        break
                    post = Post(raw)
                    if "subreddit" not in post._data and subreddit:
                        post._data["subreddit"] = subreddit
                    if post.id not in seen and self.filters.is_valid_post(post):
                        with lock:
                            if post.id not in seen:
                                seen.add(post.id)
                                rows.append(post.to_dict())
                                matched.append(post.id)
                if rows:
                    streamer.write_batch(rows)
                if reached_end:
                    break
        return matched

    def scrape_posts(
        self,
        subreddits: Union[str, List[str]],
        from_dt: Union[datetime, str, int, float],
        to_dt: Optional[Union[datetime, str, int, float]] = None,
        output_path: str = "data/curated_posts.parquet",
        storage_cls: Optional[Type[Storage]] = None,
    ) -> list[str]:
        subs = [subreddits] if isinstance(subreddits, str) else list(subreddits)
        if os.path.exists(output_path):
            os.remove(output_path)

        shards, start_dt, end_dt = self._generate_shards(from_dt, to_dt)
        seen, lock, all_matched = set(), threading.Lock(), []

        print(f"[*] Post scan using [{self.source.name}] across {len(subs)} subreddits ({start_dt:%Y-%m-%d} to {end_dt:%Y-%m-%d})")
        with (storage_cls or self.storage_cls)(output_path) as streamer:
            for sub in subs:
                with ThreadPoolExecutor(max_workers=self.post_workers) as executor:
                    futures = [executor.submit(self._scan_shard, sub, a, b, streamer, seen, lock) for a, b in shards]
                    for f in tqdm(as_completed(futures), total=len(futures), desc=f"r/{sub}"):
                        all_matched.extend(f.result())

        unique_ids = list(dict.fromkeys(all_matched))
        if unique_ids:
            print(f"[✓] Saved {len(unique_ids):,} posts to {output_path}")
        return unique_ids

    async def _scrape_comments_async(self, post_ids: list[str], output_path: str, chunk_size: int = 500, storage_cls: Optional[Type[Storage]] = None) -> int:
        if os.path.exists(output_path):
            os.remove(output_path)

        sem = asyncio.Semaphore(self.comment_workers)
        total_saved, buffer = 0, []

        async def _fetch(client: httpx.AsyncClient, pid: str):
            async with sem:
                cid, raw, _ = await self.source.fetch_comments_for_post(client, pid, fields=self.filters.required_comment_fields)
            return [c.to_dict() for raw_c in (raw or []) if self.filters.is_valid_comment(c := Comment(raw_c, cid))]

        print(f"[*] Fetching comments using [{self.source.name}] for {len(post_ids):,} posts...")
        with (storage_cls or self.storage_cls)(output_path) as streamer:
            async with httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=20, max_connections=20)) as client:
                tasks = [_fetch(client, pid) for pid in post_ids]
                for fut in async_tqdm.as_completed(tasks, total=len(tasks), desc="Comments"):
                    comments = await fut
                    if comments:
                        buffer.extend(comments)
                    if len(buffer) >= chunk_size:
                        streamer.write_batch(buffer)
                        total_saved += len(buffer)
                        buffer.clear()
                if buffer:
                    streamer.write_batch(buffer)
                    total_saved += len(buffer)

        if total_saved > 0:
            print(f"[✓] Saved {total_saved:,} comments to {output_path}")
        return total_saved

    def scrape_comments(
        self,
        post_ids: Union[str, list[str]],
        output_path: str = "data/curated_comments.parquet",
        chunk_size: int = 500,
        storage_cls: Optional[Type[Storage]] = None,
    ) -> int:
        pids = [post_ids] if isinstance(post_ids, str) else list(post_ids)
        if not pids:
            return 0
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        coro = self._scrape_comments_async(pids, output_path, chunk_size, storage_cls)
        if loop and loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(coro)
        return asyncio.run(coro)

    def run(
        self,
        subreddits: Union[str, List[str]],
        from_dt: Union[datetime, str],
        to_dt: Optional[Union[datetime, str]] = None,
        posts_output: str = "data/curated_posts.parquet",
        comments_output: str = "data/curated_comments.parquet",
        storage_cls: Optional[Type[Storage]] = None,
    ) -> tuple[list[str], int]:
        posts = self.scrape_posts(subreddits, from_dt, to_dt, posts_output, storage_cls)
        comments = self.scrape_comments(posts, comments_output, storage_cls=storage_cls) if posts else 0
        return posts, comments
