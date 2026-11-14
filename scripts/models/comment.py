"""
Comment data model for Reddit comments.
"""
from typing import Dict, Any
from scripts.models.enums import CommentField
from scripts.models.base import RedditEntity


class Comment(RedditEntity):
    """
    Representation of an Arctic Shift Reddit comment.
    Dynamically supports all 60 CommentField enumerations.
    """
    _field_enum = CommentField

    def __init__(self, data: Dict[str, Any], post_id: str = ""):
        raw = data.get("comment") or data.get("data") or data
        super().__init__(raw)

        # Normalize ID aliases
        if post_id and "post_id" not in self._data:
            self._data["post_id"] = str(post_id).replace("t3_", "")
        elif "post_id" not in self._data and "link_id" in self._data:
            self._data["post_id"] = str(self._data["link_id"]).replace("t3_", "")
        elif "post_id" not in self._data and str(self._data.get("parent_id", "")).startswith("t3_"):
            self._data["post_id"] = str(self._data["parent_id"]).replace("t3_", "")
        if "comment_id" not in self._data:
            self._data["comment_id"] = str(self._data.get("id") or self._data.get("name") or "None")
        if "id" not in self._data:
            self._data["id"] = self._data["comment_id"]

    @classmethod
    def from_api_dict(cls, raw: Dict[str, Any], post_id: str = "") -> "Comment":
        return cls(raw, post_id=post_id)

    @property
    def is_automod(self) -> bool:
        """Helper to check if comment was authored by AutoModerator."""
        author = str(self.author or "")
        return author.strip().lower() == "automoderator"

    @property
    def is_top_level(self) -> bool:
        """Helper to check if comment is a direct reply to the post (starts with t3_)."""
        parent = str(self.parent_id or "")
        return parent.startswith("t3_")

    def __repr__(self) -> str:
        cid = self._data.get("comment_id", "")
        author = self._data.get("author", "")
        return f"<Comment id={cid!r} author={author!r}>"
