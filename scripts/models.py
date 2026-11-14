"""
Data models representing Arctic Shift Reddit posts and comments.
Retains 100% of raw fields in memory, allowing users to select what is important
(include_fields) and what is not important (exclude_fields) when saving.
Validates field access and field names against the PostField and CommentField enumerations.
"""
from typing import Dict, Any, Optional, Iterable, Union, Set
from scripts.enums import PostField, CommentField, FieldEnum


def filter_dict_fields(
    data: Dict[str, Any],
    include: Optional[Iterable[Union[str, FieldEnum]]] = None,
    exclude: Optional[Iterable[Union[str, FieldEnum]]] = None,
) -> Dict[str, Any]:
    """Filters a dictionary based on whitelisted (important) or blacklisted (unimportant) keys."""
    res = dict(data)
    if include:
        include_set = {str(k) for k in include}
        res = {k: v for k, v in res.items() if k in include_set}
    if exclude:
        exclude_set = {str(k) for k in exclude}
        res = {k: v for k, v in res.items() if k not in exclude_set}
    return res


class Post:
    """
    Representation of an Arctic Shift Reddit post.
    Retains all fields, allowing user to filter which fields are saved.
    Validates field access against the PostField enumeration.
    """

    def __init__(self, data: Dict[str, Any]):
        self._data = dict(data)

    @classmethod
    def from_api_dict(cls, data: Dict[str, Any]) -> "Post":
        return cls(data)

    def to_dict(
        self,
        include_fields: Optional[Iterable[Union[str, PostField]]] = None,
        exclude_fields: Optional[Iterable[Union[str, PostField]]] = None,
    ) -> Dict[str, Any]:
        """Returns the dictionary filtered to only what the user deems important."""
        return filter_dict_fields(self._data, include=include_fields, exclude=exclude_fields)

    def __getattr__(self, name: str) -> Any:
        if name in self._data:
            return self._data[name]
        if PostField.has_field(name):
            return None
        # Attempt validation to produce a helpful error message with typo suggestion
        try:
            PostField.validate(name)
        except ValueError as e:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'. {e}") from None
        return None

    def __getitem__(self, key: Union[str, PostField]) -> Any:
        key_str = key.value if isinstance(key, PostField) else str(key)
        return self._data.get(key_str)

    def get(self, key: Union[str, PostField], default: Any = None) -> Any:
        key_str = key.value if isinstance(key, PostField) else str(key)
        return self._data.get(key_str, default)

    def __contains__(self, key: Union[str, PostField]) -> bool:
        key_str = key.value if isinstance(key, PostField) else str(key)
        return key_str in self._data

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()

    @property
    def id(self) -> str:
        return str(self._data.get("id") or "")

    @property
    def score(self) -> int:
        return int(self._data.get("score") or 0)

    @property
    def num_comments(self) -> int:
        return int(self._data.get("num_comments") or 0)

    @property
    def url(self) -> str:
        return str(self._data.get("url") or "")

    @property
    def title(self) -> str:
        return str(self._data.get("title") or "")

    @property
    def selftext(self) -> str:
        return str(self._data.get("selftext") or "")

    @property
    def flair(self) -> str:
        return str(self._data.get("link_flair_text") or self._data.get("flair") or "")

    @property
    def is_image(self) -> bool:
        """Helper to check if URL points to an image (.png, .jpg, .jpeg, or i.redd.it)."""
        clean = (self.url or "").lower().split("?")[0].strip()
        return clean.endswith((".png", ".jpg", ".jpeg")) or ("i.redd.it" in clean)

    def __repr__(self) -> str:
        return f"<Post id={self.id!r} score={self.score} num_comments={self.num_comments} title={self.title[:30]!r}>"


class Comment:
    """
    Representation of an Arctic Shift Reddit comment.
    Retains all fields, allowing user to filter which fields are saved.
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
        # Attempt validation to produce a helpful error message with typo suggestion
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
