"""
Base model class and utilities for Reddit entity data models.
"""
from typing import Dict, Any, Optional, Iterable, Union, Type
from scripts.models.enums import FieldEnum


class UnretrievedFieldError(KeyError):
    """Raised when accessing an API field that was not retrieved in the payload."""
    pass


class RedditEntity:
    """
    Base data container for Reddit API entities.
    Provides dynamic field access, typo validation, and dictionary proxy methods.
    """
    _field_enum: Type[FieldEnum]

    def __init__(self, data: Dict[str, Any]):
        self._data = dict(data)

    def to_dict(self) -> Dict[str, Any]:
        """Returns a copy of the underlying entity dictionary."""
        return dict(self._data)

    def __getattr__(self, name: str) -> Any:
        # Check if field is present in the dictionary
        if name in self._data:
            return self._data[name]

        # Check if the field is a valid entity field
        enum_cls = getattr(type(self), "_field_enum", None)
        if enum_cls and not enum_cls.has_field(name):
            try:
                enum_cls.validate(name)
            except ValueError as e:
                raise AttributeError(f"'{type(self).__name__}' has no field '{name}'. {e}") from None

        # Known entity field, but was not retrieved from the server
        raise UnretrievedFieldError(
            f"Field '{name}' was not retrieved from the server for this {type(self).__name__.lower()}. "
            f"Available fields: {sorted(list(self._data.keys()))}."
        )

    def __getitem__(self, key: Union[str, FieldEnum]) -> Any:
        key_str = key.value if isinstance(key, FieldEnum) else str(key)
        return getattr(self, key_str)

    def get(self, key: Union[str, FieldEnum], default: Any = None) -> Any:
        try:
            val = self[key]
            return default if val is None else val
        except (AttributeError, UnretrievedFieldError):
            return default

    def __contains__(self, key: Union[str, FieldEnum]) -> bool:
        key_str = key.value if isinstance(key, FieldEnum) else str(key)
        return key_str in self._data

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()
