"""
Post data model for Reddit posts.
"""
from typing import Dict, Any, Optional, Iterable, Union
from scripts.models.enums import PostField, FieldEnum


def filter_dict_fields(
    data: Dict[str, Any],
    include: Optional[Iterable[Union[str, FieldEnum]]] = None,
    exclude: Optional[Iterable[Union[str, FieldEnum]]] = None,
) -> Dict[str, Any]:
    """Filters a dictionary based on whitelisted (include) or blacklisted (exclude) keys."""
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
    Retains all fields in memory, allowing users to filter which fields are saved.
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
