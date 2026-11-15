"""
Sequential scraper baseline implementation.
Simulates traditional single-threaded, in-memory scraping without concurrency,
server-side field projection, or chunked disk streaming.
"""
import time
import asyncio
from typing import List, Dict, Any, Optional, Tuple, Callable
import requests
import httpx

from deepsift.sources.dummy import DummySource


class SequentialScraper:
    """Standard single-threaded scraper baseline accumulating raw payloads in memory."""

    BASE_URL = "https://arctic-shift.photon-reddit.com"

    def __init__(
        self,
        source_type: str = "dummy",
        dummy_seed: int = 42,
        post_filter: Optional[Callable[[Dict[str, Any]], bool]] = None,
        comment_filter: Optional[Callable[[Dict[str, Any]], bool]] = None,
        timeout: float = 15.0,
        rate_limit_delay: float = 0.2,
        simulated_latency: float = 0.0,
    ):
        self.source_type = source_type
        self.dummy_seed = dummy_seed
        self.post_filter = post_filter or (lambda _: True)
        self.comment_filter = comment_filter or (lambda _: True)
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self.simulated_latency = max(0.0, float(simulated_latency))

    def scrape_posts(
        self,
        subreddit: str,
        after_ts: int,
        before_ts: int,
        dummy_posts_per_shard: int = 100,
    ) -> List[Dict[str, Any]]:
        """Sequentially paginates and collects posts without server-side field projection."""
        matched_posts = []

        if self.source_type == "dummy":
            dummy = DummySource(
                posts_per_shard=dummy_posts_per_shard,
                batch_size=dummy_posts_per_shard,
                seed=self.dummy_seed,
                simulated_latency=self.simulated_latency,
            )
            cur = after_ts
            while cur < before_ts:
                nxt = min(cur + 86400, before_ts)
                for batch in dummy.fetch_posts_shard(subreddit, cur, nxt, fields=None):
                    matched_posts.extend(p for p in batch if self.post_filter(p))
                cur = nxt
            return matched_posts

        current_before = before_ts
        with requests.Session() as session:
            session.headers.update({"User-Agent": "deepsift-baseline-benchmark/0.2.0"})
            while current_before > after_ts:
                data = None
                for attempt in range(3):
                    try:
                        res = session.get(
                            f"{self.BASE_URL}/api/posts/search",
                            params={"subreddit": subreddit, "limit": 100, "before": current_before, "after": after_ts},
                            timeout=self.timeout,
                        )
                        if res.status_code == 200:
                            data = res.json().get("data", [])
                            break
                        time.sleep(1.0)
                    except requests.RequestException:
                        if attempt < 2:
                            time.sleep(1.5)
                        else:
                            raise

                if not data:
                    break

                matched_posts.extend(p for p in data if self.post_filter(p))
                oldest = min(int(float(p.get("created_utc", current_before))) for p in data)
                if oldest <= after_ts:
                    break
                current_before = current_before - 1 if oldest >= current_before else oldest
                time.sleep(self.rate_limit_delay)

        return matched_posts

    def scrape_comments(
        self,
        post_ids: List[str],
        dummy_comments_per_post: int = 5,
    ) -> List[Dict[str, Any]]:
        """Sequentially fetches comments one-by-one without connection pooling."""
        all_comments = []

        if self.source_type == "dummy":
            dummy = DummySource(comments_per_post=dummy_comments_per_post, seed=self.dummy_seed)
            for pid in post_ids:
                clean_id = str(pid).replace("t3_", "")
                async def _fetch_one():
                    async with httpx.AsyncClient() as client:
                        return await dummy.fetch_comments_for_post(client, clean_id, fields=None)
                _, raw, _ = asyncio.run(_fetch_one())
                all_comments.extend(c for c in raw if self.comment_filter(c))
            return all_comments

        with requests.Session() as session:
            session.headers.update({"User-Agent": "deepsift-baseline-benchmark/0.2.0"})
            for pid in post_ids:
                clean_id = str(pid).replace("t3_", "")
                try:
                    res = session.get(
                        f"{self.BASE_URL}/api/comments/tree",
                        params={"link_id": f"t3_{clean_id}"},
                        timeout=self.timeout,
                    )
                    if res.status_code == 200:
                        payload = res.json()
                        raw = payload.get("data") or payload.get("comments") or payload
                        all_comments.extend(c for c in self._flatten_nodes(raw, clean_id) if self.comment_filter(c))
                    time.sleep(self.rate_limit_delay)
                except requests.RequestException:
                    continue

        return all_comments

    def run(
        self,
        subreddit: str,
        after_ts: int,
        before_ts: int,
        dummy_posts_per_shard: int = 100,
        dummy_comments_per_post: int = 5,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Runs sequential scraping workflow and returns posts and comments."""
        posts = self.scrape_posts(subreddit, after_ts, before_ts, dummy_posts_per_shard)
        comments = self.scrape_comments([p["id"] for p in posts], dummy_comments_per_post)
        return posts, comments

    def _flatten_nodes(self, nodes: Any, post_id: str) -> List[Dict[str, Any]]:
        """Flattens nested comment tree structure into single list of comment dicts."""
        stack = list(reversed(nodes if isinstance(nodes, list) else [nodes] if isinstance(nodes, dict) else []))
        flat = []
        while stack:
            node = stack.pop()
            if not isinstance(node, dict):
                continue
            raw = node.get("comment") or node.get("data") or (node if "body" in node or "id" in node else None)
            replies = node.get("replies") or node.get("children") or (raw.get("replies") if raw else None) or []
            if isinstance(replies, dict):
                replies = replies.get("data", {}).get("children", []) if "data" in replies else list(replies.values())
            if isinstance(replies, list):
                stack.extend(reversed(replies))
            if raw and isinstance(raw, dict):
                c = dict(raw)
                c.setdefault("post_id", post_id)
                flat.append(c)
        return flat
