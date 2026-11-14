"""
Generalized Reddit Scraper Library.
Coordinates parallel shard post scanning and async comment extraction.
"""
import os
import json
import asyncio
import threading
from datetime import datetime, date, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Union, Optional, Tuple, Type
import requests
import httpx
from tqdm import tqdm
from tqdm.asyncio import tqdm as async_tqdm

from scripts.models import Post, Comment, UnretrievedFieldError
from scripts.filters import Filters
from scripts.sources import Source, ArcticShiftSource
from scripts.storage import Storage, ParquetStorage


def to_utc_datetime(val: Union[datetime, date, str, int, float, None]) -> Optional[datetime]:
    """Normalizes input to timezone-aware UTC datetime."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val, tz=timezone.utc)
    if isinstance(val, datetime):
        return val.astimezone(timezone.utc) if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day, tzinfo=timezone.utc)
    if isinstance(val, str):
        v = val.strip().strip("'\"")
        try:
            num = float(v)
            return datetime.fromtimestamp(num, tz=timezone.utc)
        except ValueError:
            pass
        v = v.replace("Z", "+00:00")
        try:
            val = datetime.fromisoformat(v)
        except ValueError:
            val = datetime.strptime(v, "%Y-%m-%d")
        return val.astimezone(timezone.utc) if val.tzinfo else val.replace(tzinfo=timezone.utc)
    raise TypeError(f"Expected datetime, date, numeric timestamp, or str date, got {type(val).__name__}")


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
        if post_workers <= 0:
            raise ValueError(f"post_workers must be positive integer >= 1, got {post_workers}")
        if comment_workers <= 0:
            raise ValueError(f"comment_workers must be positive integer >= 1, got {comment_workers}")
        if shard_days <= 0:
            raise ValueError(f"shard_days must be positive integer >= 1, got {shard_days}")

        self.filters = filters or Filters()
        self.source = source or ArcticShiftSource()
        self.storage_cls = storage_cls
        self.post_workers = post_workers
        self.comment_workers = comment_workers
        self.shard_days = shard_days
        self.errors: List[dict] = []
        self._errors_lock = threading.Lock()
        self.succeeded_posts: List[str] = []
        self.succeeded_comments: int = 0
        self.targeted_subreddits: List[str] = []
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

    def save_errors_log(
        self, errors_path: str = "data/errors.json", fatal_error: Optional[BaseException] = None
    ) -> Optional[str]:
        """Saves a structured JSON log of all failed requests, successes, and timestamps."""
        if fatal_error:
            fatal_entry = {
                "stage": "fatal_pipeline_error",
                "error_type": type(fatal_error).__name__,
                "error_message": str(fatal_error) or "Execution interrupted by user or system signal",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            with self._errors_lock:
                self.errors.append(fatal_entry)

        if not self.errors:
            return None

        dir_path = os.path.dirname(os.path.abspath(errors_path))
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        end_dt = self.completed_at or datetime.now(timezone.utc)
        duration = (end_dt - self.started_at).total_seconds() if self.started_at else None

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "failed" if fatal_error else "completed_with_errors",
            "execution": {
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "completed_at": end_dt.isoformat(),
                "duration_seconds": round(duration, 2) if duration is not None else None,
                "source": getattr(self.source, "name", "unknown"),
            },
            "summary": {
                "total_errors": len(self.errors),
                "total_posts_succeeded": len(self.succeeded_posts),
                "total_comments_succeeded": self.succeeded_comments,
            },
            "succeeded": {
                "posts_count": len(self.succeeded_posts),
                "comments_count": self.succeeded_comments,
                "subreddits": list(self.targeted_subreddits),
                "post_ids": self.succeeded_posts[:1000],
            },
            "failures": list(self.errors),
        }
        with open(errors_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        print(f"\n[!] {len(self.errors)} error(s) occurred during execution.")
        print(f"    Refer to '{errors_path}' to see what failed, what succeeded, and full timestamps.")
        return errors_path

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
        try:
            with requests.Session() as session:
                for batch in self.source.fetch_posts_shard(subreddit, after_ts, before_ts, fields=self.filters.required_post_fields, session=session):
                    rows = []
                    for raw in batch:
                        try:
                            if not isinstance(raw, dict):
                                continue
                            if int(float(raw.get("created_utc", 0))) < after_ts:
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
                        except UnretrievedFieldError:
                            raise
                        except Exception:
                            continue
                    if rows:
                        with lock:
                            streamer.write_batch(rows)
                    if reached_end:
                        break
        except Exception as e:
            error_entry = {
                "stage": "post_shard",
                "subreddit": subreddit,
                "time_window": {
                    "after_ts": after_ts,
                    "before_ts": before_ts,
                    "after_utc": datetime.fromtimestamp(after_ts, tz=timezone.utc).isoformat(),
                    "before_utc": datetime.fromtimestamp(before_ts, tz=timezone.utc).isoformat(),
                },
                "error_type": type(e).__name__,
                "error_message": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            with self._errors_lock:
                self.errors.append(error_entry)
            print(f"[!] Warning: Shard [{after_ts}, {before_ts}] for r/{subreddit} encountered an error: {e}")
        return matched

    def scrape_posts(
        self,
        subreddits: Union[str, List[str]],
        from_dt: Union[datetime, str, int, float],
        to_dt: Optional[Union[datetime, str, int, float]] = None,
        output_path: str = "data/curated_posts.parquet",
        storage_cls: Optional[Type[Storage]] = None,
        errors_output: str = "data/errors.json",
        _in_pipeline: bool = False,
    ) -> list[str]:
        subs = [subreddits] if isinstance(subreddits, str) else list(subreddits)
        if not _in_pipeline:
            self.started_at = datetime.now(timezone.utc)
            self.targeted_subreddits = subs
            self.succeeded_posts = []

        if os.path.exists(output_path):
            os.remove(output_path)

        fatal_exc = None
        unique_ids = []
        try:
            shards, start_dt, end_dt = self._generate_shards(from_dt, to_dt)
            seen, lock, all_matched = set(), threading.Lock(), []

            print(f"[*] Post scan using [{self.source.name}] across {len(subs)} subreddits ({start_dt:%Y-%m-%d} to {end_dt:%Y-%m-%d})")
            with (storage_cls or self.storage_cls)(output_path) as streamer:
                for sub in subs:
                    executor = ThreadPoolExecutor(max_workers=self.post_workers)
                    try:
                        futures = [executor.submit(self._scan_shard, sub, a, b, streamer, seen, lock) for a, b in shards]
                        for f in tqdm(as_completed(futures), total=len(futures), desc=f"r/{sub}"):
                            all_matched.extend(f.result())
                    finally:
                        executor.shutdown(wait=False, cancel_futures=True)

            unique_ids = list(dict.fromkeys(all_matched))
            self.succeeded_posts = unique_ids
            if unique_ids:
                print(f"[✓] Saved {len(unique_ids):,} posts to {output_path}")
            return unique_ids
        except BaseException as e:
            fatal_exc = e
            raise
        finally:
            if not _in_pipeline:
                self.completed_at = datetime.now(timezone.utc)
                self.save_errors_log(errors_path=errors_output, fatal_error=fatal_exc)

    async def _scrape_comments_async(
        self,
        post_ids: list[str],
        output_path: str,
        chunk_size: int = 500,
        storage_cls: Optional[Type[Storage]] = None,
        errors_output: str = "data/errors.json",
        _in_pipeline: bool = False,
    ) -> int:
        if not _in_pipeline and self.started_at is None:
            self.started_at = datetime.now(timezone.utc)

        if os.path.exists(output_path):
            os.remove(output_path)

        sem = asyncio.Semaphore(self.comment_workers)
        total_saved, buffer = 0, []
        fatal_exc = None

        async def _fetch(client: httpx.AsyncClient, pid: str):
            try:
                async with sem:
                    cid, raw, success = await self.source.fetch_comments_for_post(client, pid, fields=self.filters.required_comment_fields)
                if not success:
                    error_entry = {
                        "stage": "comment_fetch",
                        "post_id": pid,
                        "error_type": "FetchFailed",
                        "error_message": "Data source reported failure (all retries exhausted)",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    with self._errors_lock:
                        self.errors.append(error_entry)
                return [c.to_dict() for raw_c in (raw or []) if self.filters.is_valid_comment(c := Comment(raw_c, cid))]
            except Exception as e:
                error_entry = {
                    "stage": "comment_fetch",
                    "post_id": pid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                with self._errors_lock:
                    self.errors.append(error_entry)
                return []

        try:
            print(f"[*] Fetching comments using [{self.source.name}] for {len(post_ids):,} posts...")
            max_conn = max(self.comment_workers * 2, 20)
            with (storage_cls or self.storage_cls)(output_path) as streamer:
                async with httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=max_conn, max_connections=max_conn)) as client:
                    tasks = [_fetch(client, pid) for pid in post_ids]
                    for fut in async_tqdm.as_completed(tasks, total=len(tasks), desc="Comments"):
                        comments = await fut
                        if comments:
                            buffer.extend(comments)
                        if len(buffer) >= chunk_size:
                            await asyncio.to_thread(streamer.write_batch, list(buffer))
                            total_saved += len(buffer)
                            buffer.clear()
                    if buffer:
                        await asyncio.to_thread(streamer.write_batch, list(buffer))
                        total_saved += len(buffer)

            self.succeeded_comments += total_saved
            if total_saved > 0:
                print(f"[✓] Saved {total_saved:,} comments to {output_path}")
            return total_saved
        except BaseException as e:
            fatal_exc = e
            raise
        finally:
            if not _in_pipeline:
                self.completed_at = datetime.now(timezone.utc)
                self.save_errors_log(errors_path=errors_output, fatal_error=fatal_exc)

    def scrape_comments(
        self,
        post_ids: Union[str, list[str]],
        output_path: str = "data/curated_comments.parquet",
        chunk_size: int = 500,
        storage_cls: Optional[Type[Storage]] = None,
        errors_output: str = "data/errors.json",
        _in_pipeline: bool = False,
    ) -> int:
        pids = [post_ids] if isinstance(post_ids, str) else list(dict.fromkeys(post_ids))
        if not pids:
            return 0
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        coro = self._scrape_comments_async(
            pids, output_path, chunk_size, storage_cls, errors_output=errors_output, _in_pipeline=_in_pipeline
        )
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
        errors_output: str = "data/errors.json",
        storage_cls: Optional[Type[Storage]] = None,
    ) -> tuple[list[str], int]:
        subs = [subreddits] if isinstance(subreddits, str) else list(subreddits)
        self.started_at = datetime.now(timezone.utc)
        self.targeted_subreddits = subs
        self.succeeded_posts = []
        self.succeeded_comments = 0
        fatal_exc = None
        posts = []
        comments = 0

        try:
            posts = self.scrape_posts(
                subreddits=subs,
                from_dt=from_dt,
                to_dt=to_dt,
                output_path=posts_output,
                storage_cls=storage_cls,
                errors_output=errors_output,
                _in_pipeline=True,
            )
            if posts:
                comments = self.scrape_comments(
                    post_ids=posts,
                    output_path=comments_output,
                    storage_cls=storage_cls,
                    errors_output=errors_output,
                    _in_pipeline=True,
                )
            return posts, comments
        except BaseException as e:
            fatal_exc = e
            raise
        finally:
            self.completed_at = datetime.now(timezone.utc)
            self.save_errors_log(errors_path=errors_output, fatal_error=fatal_exc)
