"""
Comment data model for Reddit comments.
"""
from typing import Dict, Any, Optional, Iterable, Union
from scripts.models.enums import CommentField
from scripts.models.post import filter_dict_fields


class Comment:
    """
    Representation of an Arctic Shift Reddit comment.
    Retains all fields, allowing users to filter which fields are saved.
    Validates field access against the CommentField enumeration.
    """

    def __init__(self, data: Dict[str, Any], post_id: str = ""):
        raw = data.get("comment") or data.get("data") or data
        self._data = dict(raw)
        if post_id and "post_id" not in self._data:
            self._data["post_id"] = str(post_id).replace("t3_", "")
        if "comment_id" not in self._data:
            self._data["comment_id"] = str(self._data.get("id") or self._data.get("name") or "None")

    @classmethod
    def from_api_dict(cls, raw: Dict[str, Any], post_id: str = "") -> "Comment":
        return cls(raw, post_id)

    def to_dict(
        self,
        include_fields: Optional[Iterable[Union[str, CommentField]]] = None,
        exclude_fields: Optional[Iterable[Union[str, CommentField]]] = None,
    ) -> Dict[str, Any]:
        """Returns the dictionary filtered to only what the user deems important."""
        return filter_dict_fields(self._data, include=include_fields, exclude=exclude_fields)

    def __getattr__(self, name: str) -> Any:
        if name in self._data:
            return self._data[name]
        if CommentField.has_field(name):
            return None
        try:
            CommentField.validate(name)
        except ValueError as e:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'. {e}") from None
        return None

    def __getitem__(self, key: Union[str, CommentField]) -> Any:
        key_str = key.value if isinstance(key, CommentField) else str(key)
        return self._data.get(key_str)

    def get(self, key: Union[str, CommentField], default: Any = None) -> Any:
        key_str = key.value if isinstance(key, CommentField) else str(key)
        return self._data.get(key_str, default)

    def __contains__(self, key: Union[str, CommentField]) -> bool:
        key_str = key.value if isinstance(key, CommentField) else str(key)
        return key_str in self._data

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()

    @property
    def comment_id(self) -> str:
        return str(self._data.get("comment_id") or self._data.get("id") or "None")

    @property
    def post_id(self) -> str:
        return str(self._data.get("post_id") or "")

    @property
    def author(self) -> str:
        return str(self._data.get("author") or "[deleted]")

    @property
    def body(self) -> str:
        return str(self._data.get("body") or "")

    @property
    def score(self) -> int:
        return int(self._data.get("score") or 0)

    @property
    def parent_id(self) -> str:
        return str(self._data.get("parent_id") or "")

    @property
    def is_automod(self) -> bool:
        return self.author.strip().lower() == "automoderator"

    @property
    def is_top_level(self) -> bool:
        return self.parent_id.startswith("t3_")

    def __repr__(self) -> str:
        return f"<Comment id={self.comment_id!r} author={self.author!r} score={self.score}>"
