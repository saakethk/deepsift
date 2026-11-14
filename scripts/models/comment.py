"""
Comment data model for Reddit comments.
"""
from typing import Dict, Any
from scripts.models.enums import CommentField
from scripts.models.base import RedditEntity


class Comment(RedditEntity):
    """
    Representation of a Reddit comment.
    Dynamically supports all CommentField enumerations.
    """
    _field_enum = CommentField
    REQUIRED_FIELDS = frozenset({"id", "post_id", "parent_id"})

    def __init__(self, data: Dict[str, Any], post_id: str = ""):
        super().__init__(data)
        if "id" in self._data and isinstance(self._data["id"], str):
            self._data["id"] = self._data["id"].replace("t1_", "")
        if "post_id" in self._data and isinstance(self._data["post_id"], str):
            self._data["post_id"] = self._data["post_id"].replace("t3_", "")
        elif post_id:
            self._data["post_id"] = str(post_id).replace("t3_", "")

    @classmethod
    def from_api_dict(cls, data: Dict[str, Any], post_id: str = "") -> "Comment":
        return cls(data, post_id=post_id)

    @property
    def is_top_level(self) -> bool:
        """Helper to check if comment is a direct reply to the post (starts with t3_)."""
        parent = str(self.get("parent_id") or "")
        return parent.startswith("t3_")

    def __repr__(self) -> str:
        cid = self._data.get("id", "")
        return f"<Comment id={cid!r}>"
