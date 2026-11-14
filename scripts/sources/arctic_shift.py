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
        close_session = session is None
        s = session or requests.Session()
        current_before = before_ts
        projected = self.resolve_post_fields(fields)
        fields_str = ",".join(sorted(projected)) if projected else None

        try:
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
                if oldest <= after_ts:
                    break
                current_before = current_before - 1 if oldest >= current_before else oldest
                time.sleep(self.rate_limit_delay)
        finally:
            if close_session:
                s.close()

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
            except Exception:
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

            if not raw_comment:
                continue

            comment_dict = dict(raw_comment)
            if "post_id" not in comment_dict:
                comment_dict["post_id"] = post_id
            flat.append(comment_dict)

        return flat

    async def _fetch_search_fallback(
        self, client: httpx.AsyncClient, clean_id: str, fields: Optional[Iterable[str]] = None
    ) -> List[Dict[str, Any]]:
        """Fallback to /api/comments/search with field projection and backward pagination."""
        all_comments = []
        seen_ids = set()
        projected = self.resolve_comment_fields(fields)
        query_fields = (set(projected) | {"id", "created_utc"}) if projected else None
        fields_str = ",".join(sorted(query_fields)) if query_fields else None
        current_before = None

        for _ in range(25):
            params = {"link_id": f"t3_{clean_id}", "limit": self.batch_size}
            if fields_str:
                params["fields"] = fields_str
            if current_before is not None:
                params["before"] = current_before

            try:
                resp = await client.get(
                    f"{self.base_url}/api/comments/search",
                    params=params,
                    headers=self.headers,
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    raw = resp.json().get("data", [])
                    if not raw:
                        break
                    for item in raw:
                        cid = str(item.get("id", ""))
                        if cid and cid in seen_ids:
                            continue
                        if cid:
                            seen_ids.add(cid)
                        if "post_id" not in item:
                            item["post_id"] = clean_id
                        all_comments.append(item)
                    if len(raw) < self.batch_size:
                        break
                    oldest_ts = raw[-1].get("created_utc")
                    if oldest_ts is not None:
                        try:
                            oldest_int = int(oldest_ts)
                            current_before = oldest_int - 1 if (current_before is not None and oldest_int >= current_before) else oldest_int
                        except (ValueError, TypeError):
                            break
                    else:
                        break
                else:
                    break
            except Exception:
                break

        return all_comments
