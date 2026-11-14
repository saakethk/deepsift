"""
Abstract base class definition for Reddit data sources.
"""
from abc import ABC, abstractmethod
from typing import Iterator, List, Dict, Any, Optional, Tuple, Iterable
import requests
import httpx


class Source(ABC):
    """
    Abstract Base Class for Reddit data sources.
    Handles communication with specific APIs, archives, or data stores.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifying name of the data source."""
        pass

    @abstractmethod
    def fetch_posts_shard(
        self,
        subreddit: str,
        after_ts: int,
        before_ts: int,
        fields: Optional[Iterable[str]] = None,
        session: Optional[requests.Session] = None,
    ) -> Iterator[List[Dict[str, Any]]]:
        """
        Yields batches of raw post dictionaries for a given subreddit within [after_ts, before_ts].
        If fields is provided, requests only those fields from the server.
        """
        pass

    @abstractmethod
    async def fetch_comments_for_post(
        self,
        client: httpx.AsyncClient,
        post_id: str,
        fields: Optional[Iterable[str]] = None,
        max_retries: int = 5,
    ) -> Tuple[str, List[Dict[str, Any]], bool]:
        """
        Asynchronously fetches comment dictionaries for a given post.
        Returns: (post_id, comments_list, success_bool)
        """
        pass

    def fetch_comments(self, post_id: str, fields: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
        """
        Synchronously fetches comments for a single post using a transient httpx client.
        """
        import asyncio
        async def _run():
            async with httpx.AsyncClient() as client:
                _, comments, _ = await self.fetch_comments_for_post(client, post_id, fields=fields)
                return comments
        return asyncio.run(_run())


BaseSource = Source
