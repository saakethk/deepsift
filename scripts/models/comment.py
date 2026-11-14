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

    def __init__(self, data: Dict[str, Any], post_id: str = ""):
        super().__init__(data)
        if post_id and "post_id" not in self._data:
            self._data["post_id"] = str(post_id).replace("t3_", "")

    @classmethod
    def from_api_dict(cls, data: Dict[str, Any], post_id: str = "") -> "Comment":
        return cls(data, post_id=post_id)

    @property
    def is_top_level(self) -> bool:
        """Helper to check if comment is a direct reply to the post (starts with t3_)."""
        parent = str(self.parent_id or "")
        return parent.startswith("t3_")

    def __repr__(self) -> str:
        cid = self._data.get("id", "")
        return f"<Comment id={cid!r}>"
