"""
Arctic Shift API data source implementation.
"""
import time
import asyncio
from typing import Iterator, List, Dict, Any, Optional, Tuple, Iterable
import requests
import httpx
from scripts.sources.base import Source


class ArcticShiftSource(Source):
    """
    Arctic Shift API data source implementation (https://arctic-shift.photon-reddit.com).
    Supports server-side field projection via the `fields=` query parameter.
    """

    BASE_URL = "https://arctic-shift.photon-reddit.com"
    DEFAULT_USER_AGENT = "reddit-research-scraper/0.2.0"

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = 15.0,
        rate_limit_delay: float = 0.3,
        batch_size: int = 100,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self.batch_size = batch_size
        self.user_agent = user_agent
        self.headers = {"User-Agent": self.user_agent}

    @property
    def name(self) -> str:
        return "arctic_shift"

    def fetch_posts_shard(
        self,
        subreddit: str,
        after_ts: int,
        before_ts: int,
        fields: Optional[Iterable[str]] = None,
        session: Optional[requests.Session] = None,
    ) -> Iterator[List[Dict[str, Any]]]:
        """
        Paginates backwards through Arctic Shift posts in time window [after_ts, before_ts].
        If fields is specified, requests only those fields from the server.
        """
        s = session or requests.Session()
        current_before = before_ts
        projected = self.resolve_post_fields(fields)
        fields_str = ",".join(sorted(projected)) if projected else None

        while current_before > after_ts:
            params = {
                "subreddit": subreddit,
                "limit": self.batch_size,
                "before": current_before,
                "after": after_ts,
            }
            if fields_str:
                params["fields"] = fields_str

            data = None
            backoff = 2.0
            for _ in range(5):
                try:
                    res = s.get(
                        f"{self.base_url}/api/posts/search",
                        params=params,
                        headers=self.headers,
                        timeout=self.timeout,
                    )
                    if res.status_code == 200:
                        data = res.json().get("data", [])
                        break
                    time.sleep(backoff)
                    backoff *= 1.8
                except requests.RequestException:
                    time.sleep(backoff)
                    backoff *= 1.8

            if data is None:
                current_before -= 86400  # Step back 1 day on persistent network timeout
                continue

            if not data:
                break

            yield data

            oldest = int(data[-1].get("created_utc", 0))
            if oldest > after_ts:
                current_before = current_before - 1 if oldest >= current_before else oldest
            else:
                current_before -= 1
            time.sleep(self.rate_limit_delay)

    async def fetch_comments_for_post(
        self,
        client: httpx.AsyncClient,
        post_id: str,
        fields: Optional[Iterable[str]] = None,
        max_retries: int = 5,
    ) -> Tuple[str, List[Dict[str, Any]], bool]:
        """
        Fetches comments from Arctic Shift.
        Tree endpoint is attempted first; falls back to search endpoint with fields projection if needed.
        """
        clean_id = str(post_id).replace("t3_", "")
        tree_url = f"{self.base_url}/api/comments/tree"
        params = {"link_id": f"t3_{clean_id}"}
        backoff = 2.0

        for _ in range(max_retries):
            try:
                resp = await client.get(
                    tree_url,
                    params=params,
                    headers=self.headers,
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    json_data = resp.json()
                    raw = json_data.get("data")
                    if raw is None and "comments" in json_data:
                        raw = json_data["comments"]
                    cleaned = self._unpack_nodes(raw if raw is not None else json_data, clean_id)
                    if not cleaned and raw is None:
                        cleaned = await self._fetch_search_fallback(client, clean_id, fields=fields)
                    return clean_id, cleaned, True

                await asyncio.sleep(backoff)
                backoff *= 1.6
            except (httpx.RequestError, httpx.TimeoutException):
                await asyncio.sleep(backoff)
                backoff *= 1.6

        fallback = await self._fetch_search_fallback(client, clean_id, fields=fields)
        return clean_id, fallback, bool(fallback)

    def _unpack_nodes(self, nodes: Any, post_id: str) -> List[Dict[str, Any]]:
        """
        Flattens nested comment tree into raw dictionaries using a stack.
        Avoids recursion limits for deeply nested reply threads.
        """
        flat = []
        if not isinstance(nodes, list):
            nodes = [nodes] if isinstance(nodes, dict) else []

        stack = list(reversed(nodes))
        while stack:
            node = stack.pop()
            if not isinstance(node, dict):
                continue

            raw_comment = node.get("comment") or node.get("data") or node
            comment_dict = dict(raw_comment)
            if "post_id" not in comment_dict:
                comment_dict["post_id"] = post_id
            flat.append(comment_dict)

            replies = node.get("replies") or node.get("children") or []
            if isinstance(replies, list) and replies:
                for child in reversed(replies):
                    stack.append(child)

        return flat

    async def _fetch_search_fallback(
        self, client: httpx.AsyncClient, clean_id: str, fields: Optional[Iterable[str]] = None
    ) -> List[Dict[str, Any]]:
        """Fallback to /api/comments/search with field projection."""
        params = {"link_id": f"t3_{clean_id}", "limit": self.batch_size}
        projected = self.resolve_comment_fields(fields)
        if projected:
            params["fields"] = ",".join(sorted(projected))

        try:
            resp = await client.get(
                f"{self.base_url}/api/comments/search",
                params=params,
                headers=self.headers,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                raw = resp.json().get("data", [])
                for item in raw:
                    if "post_id" not in item:
                        item["post_id"] = clean_id
                return raw
        except Exception:
            pass
        return []
