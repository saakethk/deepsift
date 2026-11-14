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

    @classmethod
    def from_api_dict(cls, data: Dict[str, Any]) -> "Post":
        return cls(data)

    @property
    def has_image(self) -> bool:
        """Helper to check if post links to or contains an image (.png, .jpg, .jpeg, or i.redd.it)."""
        url = str(self.url or "")
        clean = url.lower().split("?")[0].strip()
        return clean.endswith((".png", ".jpg", ".jpeg")) or ("i.redd.it" in clean)

    def __repr__(self) -> str:
        post_id = self._data.get("id", "")
        title = self._data.get("title", "")
        return f"<Post id={post_id!r} title={title[:30]!r}>"
