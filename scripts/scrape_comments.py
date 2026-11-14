"""
Asynchronous comment tree scraper using HTTPX and Asyncio.
Features:
- Up to 5 retries with exponential backoff on 429/5xx errors
- Secondary retry pass for any failed posts
- Recursively unpacks nested trees and falls back to search endpoint
- Flushes directly to Parquet
"""
import os
import asyncio
import httpx
from tqdm.asyncio import tqdm as async_tqdm

from scripts.filters import is_valid_comment
from scripts.parsers import clean_comment, unpack_comment_tree
from scripts.parquet_streamer import ParquetStreamer


async def fetch_search_fallback(client: httpx.AsyncClient, clean_id: str) -> list[dict]:
    """Fallback to flat comment search endpoint if tree extraction fails or is empty."""
    url = f"https://arctic-shift.photon-reddit.com/api/comments/search?link_id=t3_{clean_id}&limit=100"
    try:
        resp = await client.get(url, timeout=12.0)
        if resp.status_code == 200:
            raw = resp.json().get("data", [])
            return [clean_comment(c, clean_id) for c in raw if is_valid_comment(c)]
    except Exception:
        pass
    return []


async def fetch_comments_for_post(
    client: httpx.AsyncClient, post_id: str, semaphore: asyncio.Semaphore, max_retries: int = 5
) -> tuple[str, list[dict], bool]:
    """Fetches comments for a single post using tree endpoint with fallback to search."""
    clean_id = str(post_id).replace("t3_", "")
    tree_url = f"https://arctic-shift.photon-reddit.com/api/comments/tree?link_id=t3_{clean_id}"
    backoff = 2.0

    async with semaphore:
        for _ in range(max_retries):
            try:
                resp = await client.get(tree_url, timeout=12.0)
                if resp.status_code == 200:
                    json_data = resp.json()
                    raw = json_data.get("data") or json_data.get("comments") or json_data
                    cleaned = unpack_comment_tree(raw, clean_id)
                    if not cleaned:
                        cleaned = await fetch_search_fallback(client, clean_id)
                    return clean_id, cleaned, True

                await asyncio.sleep(backoff)
                backoff *= 1.6
            except (httpx.RequestError, httpx.TimeoutException):
                await asyncio.sleep(backoff)
                backoff *= 1.6

    fallback = await fetch_search_fallback(client, clean_id)
    return clean_id, fallback, bool(fallback)


async def _scrape_comments_async(
    post_ids: list[str], output_path: str, concurrency_limit: int = 5, chunk_size: int = 500
) -> int:
    """Asynchronous orchestrator for concurrent comment extraction."""
    if os.path.exists(output_path):
        os.remove(output_path)

    limits = httpx.Limits(max_keepalive_connections=20, max_connections=20)
    semaphore = asyncio.Semaphore(concurrency_limit)
    total_saved, buffer, failed_posts = 0, [], []

    print(f"[*] Fetching comments for {len(post_ids):,} posts with {concurrency_limit} async workers...")

    with ParquetStreamer(output_path) as streamer:
        async with httpx.AsyncClient(limits=limits) as client:
            tasks = [fetch_comments_for_post(client, pid, semaphore) for pid in post_ids]

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

            # Secondary retry pass for any posts that experienced network dropouts
            if failed_posts:
                print(f"\n[*] Retrying {len(failed_posts)} failed posts...")
                await asyncio.sleep(2.0)
                retry_tasks = [fetch_comments_for_post(client, pid, semaphore, max_retries=6) for pid in failed_posts]
                for future in async_tqdm.as_completed(retry_tasks, total=len(retry_tasks), desc="Retries"):
                    _, comments, _ = await future
                    if comments:
                        buffer.extend(comments)

            if buffer:
                streamer.write_batch(buffer)
                total_saved += len(buffer)

    print(f"[✓] Comments complete. Saved {total_saved:,} comments to {output_path}")
    return total_saved


def collect_cohort_comments(
    post_ids: list[str], output_path: str = "data/curated_comments_5yr.parquet",
    concurrency_limit: int = 5, chunk_size: int = 500
) -> int:
    """Synchronous entry point that runs the async comment scraper."""
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
        return loop.run_until_complete(_scrape_comments_async(post_ids, output_path, concurrency_limit, chunk_size))
    return asyncio.run(_scrape_comments_async(post_ids, output_path, concurrency_limit, chunk_size))
