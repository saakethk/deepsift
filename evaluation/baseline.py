"""
Naive sequential baseline scraper implementation.
Simulates traditional single-threaded, in-memory scraping without
concurrency, server-side field projection, or chunked disk streaming.
"""
import time
from typing import List, Dict, Any, Optional, Tuple, Callable
import requests

from deepsift.sources.dummy import DummySource


class SequentialScraper:
    """
    Standard sequential scraper baseline.
    Fetches raw payloads without field projection and accumulates
    all records in-memory before final serialization.
    """

    BASE_URL = "https://arctic-shift.photon-reddit.com"

    def __init__(
        self,
        source_type: str = "dummy",
        dummy_seed: int = 42,
        post_filter: Optional[Callable[[Dict[str, Any]], bool]] = None,
        comment_filter: Optional[Callable[[Dict[str, Any]], bool]] = None,
        timeout: float = 15.0,
        rate_limit_delay: float = 0.3,
    ):
        self.source_type = source_type
        self.dummy_seed = dummy_seed
        self.post_filter = post_filter or (lambda p: True)
        self.comment_filter = comment_filter or (lambda c: True)
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay

    def scrape_posts(
        self,
        subreddit: str,
        after_ts: int,
        before_ts: int,
        dummy_posts_per_shard: int = 100,
    ) -> List[Dict[str, Any]]:
        """Sequentially paginates and collects posts in memory without field projection."""
        matched_posts = []

        if self.source_type == "dummy":
            dummy = DummySource(
                posts_per_shard=dummy_posts_per_shard,
                batch_size=50,
                seed=self.dummy_seed,
            )
            for batch in dummy.fetch_posts_shard(subreddit, after_ts, before_ts, fields=None):
                for post in batch:
                    if self.post_filter(post):
                        matched_posts.append(post)
            return matched_posts

        session = requests.Session()
        session.headers.update({"User-Agent": "deepsift-baseline-benchmark/0.2.0"})
        current_before = before_ts

        try:
            while current_before > after_ts:
                params = {
                    "subreddit": subreddit,
                    "limit": 100,
                    "before": current_before,
                    "after": after_ts,
                }
                res = session.get(
                    f"{self.BASE_URL}/api/posts/search",
                    params=params,
                    timeout=self.timeout,
                )
                if res.status_code != 200:
                    time.sleep(1.0)
                    continue

                data = res.json().get("data", [])
                if not data:
                    break

                for post in data:
                    if self.post_filter(post):
                        matched_posts.append(post)

                oldest = min(int(float(p.get("created_utc", current_before))) for p in data)
                if oldest <= after_ts:
                    break
                current_before = current_before - 1 if oldest >= current_before else oldest
                time.sleep(self.rate_limit_delay)
        finally:
            session.close()

        return matched_posts

    def scrape_comments(
        self,
        post_ids: List[str],
        dummy_comments_per_post: int = 5,
    ) -> List[Dict[str, Any]]:
        """Sequentially fetches comments for each post one-by-one without connection pooling."""
        all_comments = []

        if self.source_type == "dummy":
            dummy = DummySource(
                comments_per_post=dummy_comments_per_post,
                seed=self.dummy_seed,
            )
            for pid in post_ids:
                clean_id = str(pid).replace("t3_", "")
                import asyncio
                import httpx
                async def _get():
                    async with httpx.AsyncClient() as client:
                        return await dummy.fetch_comments_for_post(client, clean_id, fields=None)
                _, raw_comments, _ = asyncio.run(_get())
                for c in raw_comments:
                    if self.comment_filter(c):
                        all_comments.append(c)
            return all_comments

        session = requests.Session()
        session.headers.update({"User-Agent": "deepsift-baseline-benchmark/0.2.0"})

        try:
            for pid in post_ids:
                clean_id = str(pid).replace("t3_", "")
                url = f"{self.BASE_URL}/api/comments/tree"
                try:
                    res = session.get(
                        url,
                        params={"link_id": f"t3_{clean_id}"},
                        timeout=self.timeout,
                    )
                    if res.status_code == 200:
                        json_data = res.json()
                        raw = json_data.get("data")
                        if raw is None and "comments" in json_data:
                            raw = json_data["comments"]
                        nodes = raw if raw is not None else json_data
                        flat = self._unpack_nodes(nodes, clean_id)
                        for c in flat:
                            if self.comment_filter(c):
                                all_comments.append(c)
                    time.sleep(self.rate_limit_delay)
                except requests.RequestException:
                    continue
        finally:
            session.close()

        return all_comments

    def run(
        self,
        subreddit: str,
        after_ts: int,
        before_ts: int,
        dummy_posts_per_shard: int = 100,
        dummy_comments_per_post: int = 5,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Runs the entire sequential scraping workflow and returns collected raw lists."""
        posts = self.scrape_posts(
            subreddit=subreddit,
            after_ts=after_ts,
            before_ts=before_ts,
            dummy_posts_per_shard=dummy_posts_per_shard,
        )
        post_ids = [p["id"] for p in posts]
        comments = self.scrape_comments(
            post_ids=post_ids,
            dummy_comments_per_post=dummy_comments_per_post,
        )
        return posts, comments

    def _unpack_nodes(self, nodes: Any, post_id: str) -> List[Dict[str, Any]]:
        flat = []
        if not isinstance(nodes, list):
            nodes = [nodes] if isinstance(nodes, dict) else []
        stack = list(reversed(nodes))
        while stack:
            node = stack.pop()
            if not isinstance(node, dict):
                continue
            raw_comment = None
            if "comment" in node and isinstance(node["comment"], dict):
                raw_comment = node["comment"]
            elif "data" in node and isinstance(node["data"], dict):
                raw_comment = node["data"]
            elif "body" in node or "id" in node or "author" in node:
                raw_comment = node

            replies = node.get("replies") or node.get("children") or []
            if raw_comment and not replies:
                replies = raw_comment.get("replies") or raw_comment.get("children") or []
            if isinstance(replies, dict):
                replies = replies.get("data", {}).get("children", []) if "data" in replies else list(replies.values())
            if isinstance(replies, list) and replies:
                for child in reversed(replies):
                    stack.append(child)
            if raw_comment:
                c = dict(raw_comment)
                c["post_id"] = post_id
                flat.append(c)
        return flat
