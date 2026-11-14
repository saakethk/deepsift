"""
Asynchronous comment tree scraper using HTTPX and Asyncio.
Fixes:
- Up to 5 retries with exponential backoff on 429/5xx errors
- Secondary retry pass for any failed posts
- Recursively unpacks nested trees and falls back to search endpoint
- Flushes directly to Parquet
"""
import sys
from pathlib import Path

# Enable importing sibling modules regardless of how the script is invoked
sys.path.insert(0, str(Path(__file__).resolve().parent))

import os
import asyncio
import httpx
from tqdm.asyncio import tqdm as async_tqdm

from parquet_streamer import ParquetStreamer


def is_automod(author: str) -> bool:
    """Checks if the author is AutoModerator (case-insensitive)."""
    return str(author or "").strip().lower() == "automoderator"


def extract_comment_data(node: dict) -> dict:
    """Extracts the inner comment dictionary from tree nodes."""
    if not isinstance(node, dict):
        return {}
    if "comment" in node and isinstance(node["comment"], dict):
        return node["comment"]
    if "data" in node and isinstance(node["data"], dict):
        return node["data"]
    return node


def clean_comment(comment: dict, post_id: str) -> dict:
    """Normalizes comment fields into standard schema."""
    data = extract_comment_data(comment)
    return {
        "comment_id": str(data.get("id") or data.get("comment_id") or data.get("name") or "None"),
        "post_id": str(post_id),
        "author": str(data.get("author") or "[deleted]"),
        "body": str(data.get("body") or ""),
        "score": int(data.get("score") or 0),
        "created_utc": int(data.get("created_utc") or 0),
        "parent_id": str(data.get("parent_id") or ""),
    }


def flatten_tree(nodes: list, post_id: str) -> list[dict]:
    """Recursively unpacks comment trees and nested replies."""
    flat = []
    if not isinstance(nodes, list):
        if isinstance(nodes, dict):
            nodes = [nodes]
        else:
            return flat

    for node in nodes:
        if not isinstance(node, dict):
            continue

        # Extract the current comment (exclude AutoModerator)
        cleaned = clean_comment(node, post_id)
        if (cleaned["comment_id"] != "None" or cleaned["body"]) and not is_automod(cleaned["author"]):
            flat.append(cleaned)

        replies = node.get("replies") or node.get("children") or []
        if isinstance(replies, list) and replies:
            flat.extend(flatten_tree(replies, post_id))

    return flat


async def fetch_comments_for_post(
    client: httpx.AsyncClient,
    post_id: str,
    semaphore: asyncio.Semaphore,
    max_retries: int = 5
) -> tuple[str, list[dict], bool]:
    """
    Fetches comments for a post with exponential backoff.
    Returns: (post_id, comments_list, is_success)
    """
    clean_id = str(post_id).replace("t3_", "")
    tree_url = f"https://arctic-shift.photon-reddit.com/api/comments/tree?link_id=t3_{clean_id}"
    backoff = 2.0

    async with semaphore:
        for attempt in range(max_retries):
            try:
                resp = await client.get(tree_url, timeout=12.0)
                if resp.status_code == 200:
                    json_data = resp.json()
                    raw = json_data.get("data") or json_data.get("comments") or json_data
                    cleaned = flatten_tree(raw, clean_id)
                    
                    # If tree returned empty, try search endpoint as fallback
                    if not cleaned:
                        search_url = f"https://arctic-shift.photon-reddit.com/api/comments/search?link_id=t3_{clean_id}&limit=100"
                        res_search = await client.get(search_url, timeout=10.0)
                        if res_search.status_code == 200:
                            raw_search = res_search.json().get("data", [])
                            cleaned = [
                                clean_comment(c, clean_id)
                                for c in raw_search
                                if not is_automod(c.get("author"))
                            ]

                    return clean_id, cleaned, True

                elif resp.status_code == 429:
                    await asyncio.sleep(backoff)
                    backoff *= 1.8
                elif resp.status_code >= 500:
                    await asyncio.sleep(backoff)
                    backoff *= 1.5
            except (httpx.RequestError, httpx.TimeoutException):
                await asyncio.sleep(backoff)
                backoff *= 1.5

    # If all tree retries failed, try one final search fallback
    try:
        search_url = f"https://arctic-shift.photon-reddit.com/api/comments/search?link_id=t3_{clean_id}&limit=100"
        res_search = await client.get(search_url, timeout=12.0)
        if res_search.status_code == 200:
            raw_search = res_search.json().get("data", [])
            cleaned = [
                clean_comment(c, clean_id)
                for c in raw_search
                if not is_automod(c.get("author"))
            ]
            return clean_id, cleaned, True
    except Exception:
        pass

    return clean_id, [], False


async def _scrape_comments_async(
    post_ids: list[str],
    output_path: str,
    concurrency_limit: int = 5,
    chunk_size: int = 500
) -> int:
    """Asynchronous comment scraping pipeline with secondary retry pass."""
    if os.path.exists(output_path):
        os.remove(output_path)

    limits = httpx.Limits(max_keepalive_connections=20, max_connections=20)
    semaphore = asyncio.Semaphore(concurrency_limit)
    total_saved = 0
    buffer = []
    failed_posts = []

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

            # Secondary pass for any posts that timed out under network load
            if failed_posts:
                print(f"\n[*] Running retry pass on {len(failed_posts)} failed posts...")
                await asyncio.sleep(3.0)  # Cool-down
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
    post_ids: list[str],
    output_path: str = "data/curated_comments_5yr.parquet",
    concurrency_limit: int = 5,
    chunk_size: int = 500
) -> int:
    """Synchronous entry point that runs the resilient async scraper."""
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
        return loop.run_until_complete(
            _scrape_comments_async(post_ids, output_path, concurrency_limit, chunk_size)
        )
    else:
        return asyncio.run(
            _scrape_comments_async(post_ids, output_path, concurrency_limit, chunk_size)
        )
