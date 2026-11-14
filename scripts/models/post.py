"""
Post data model for Reddit posts.
"""
from typing import Dict, Any
from scripts.models.enums import PostField
from scripts.models.base import RedditEntity


class Post(RedditEntity):
    """
    Representation of an Arctic Shift Reddit post.
    Dynamically supports all 105 PostField enumerations.
    """
    _field_enum = PostField
    REQUIRED_FIELDS = frozenset({"id", "created_utc", "subreddit"})

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        if "id" in self._data and isinstance(self._data["id"], str):
            self._data["id"] = self._data["id"].replace("t3_", "")

    @classmethod
    def from_api_dict(cls, data: Dict[str, Any]) -> "Post":
        return cls(data)

    def __repr__(self) -> str:
        post_id = self._data.get("id", "")
        title = self._data.get("title", "")
        return f"<Post id={post_id!r} title={title[:30]!r}>" if title else f"<Post id={post_id!r}>"
