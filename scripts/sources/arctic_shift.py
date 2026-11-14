"""
Arctic Shift API data source implementation.
"""
import time
import requests
import httpx
from typing import Iterator, List, Dict, Any, Optional, Tuple, Iterable
from scripts.sources.base import Source


class ArcticShiftSource(Source):
    """
    Arctic Shift API data source implementation (https://arctic-shift.photon-reddit.com).
    Supports server-side field projection via the `fields=` query parameter.
    """

    BASE_URL = "https://arctic-shift.photon-reddit.com"

    def __init__(self, base_url: str = BASE_URL, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

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
        fields_param = f"&fields={','.join(sorted(fields))}" if fields else ""

        while current_before > after_ts:
            url = (
                f"{self.base_url}/api/posts/search"
                f"?subreddit={subreddit}&limit=100&before={current_before}&after={after_ts}{fields_param}"
            )

            data = None
            backoff = 2.0
            for _ in range(5):
                try:
                    res = s.get(url, timeout=self.timeout)
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

            oldest = data[-1]["created_utc"]
            current_before = current_before - 1 if oldest >= current_before else oldest
            time.sleep(0.3)

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
        tree_url = f"{self.base_url}/api/comments/tree?link_id=t3_{clean_id}"
        backoff = 2.0

        for _ in range(max_retries):
            try:
                resp = await client.get(tree_url, timeout=12.0)
                if resp.status_code == 200:
                    json_data = resp.json()
                    raw = json_data.get("data") or json_data.get("comments") or json_data
                    cleaned = self._unpack_nodes(raw, clean_id)
                    if not cleaned:
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
        """Flattens Arctic Shift nested comment tree into raw dictionaries."""
        flat = []
        if not isinstance(nodes, list):
            nodes = [nodes] if isinstance(nodes, dict) else []

        for node in nodes:
            if not isinstance(node, dict):
                continue
            raw_comment = node.get("comment") or node.get("data") or node
            comment_dict = dict(raw_comment)
            if "post_id" not in comment_dict:
                comment_dict["post_id"] = post_id
            flat.append(comment_dict)

            replies = node.get("replies") or node.get("children") or []
            if isinstance(replies, list) and replies:
                flat.extend(self._unpack_nodes(replies, post_id))

        return flat

    async def _fetch_search_fallback(
        self, client: httpx.AsyncClient, clean_id: str, fields: Optional[Iterable[str]] = None
    ) -> List[Dict[str, Any]]:
        """Fallback to /api/comments/search with optional field projection."""
        fields_param = f"&fields={','.join(sorted(fields))}" if fields else ""
        url = f"{self.base_url}/api/comments/search?link_id=t3_{clean_id}&limit=100{fields_param}"
        try:
            resp = await client.get(url, timeout=12.0)
            if resp.status_code == 200:
                raw = resp.json().get("data", [])
                for item in raw:
                    if "post_id" not in item:
                        item["post_id"] = clean_id
                return raw
        except Exception:
            pass
        return []
