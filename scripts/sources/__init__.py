"""
Data sources subpackage for Reddit scraping.
"""
from typing import Dict, Type
from scripts.sources.base import Source, BaseSource
from scripts.sources.arctic_shift import ArcticShiftSource

SOURCES: Dict[str, Type[Source]] = {
    "arctic_shift": ArcticShiftSource,
}


def register_source(name: str, source_cls: Type[Source]):
    """Registers a new custom Source provider."""
    SOURCES[name.lower().strip()] = source_cls


def get_source(name: str = "arctic_shift", **kwargs) -> Source:
    """Instantiates and returns a registered data source by name."""
    key = name.lower().strip()
    if key not in SOURCES:
        available = ", ".join(sorted(SOURCES.keys()))
        raise ValueError(f"Unknown data source '{name}'. Available sources: {available}")
    return SOURCES[key](**kwargs)


__all__ = [
    "Source",
    "BaseSource",
    "ArcticShiftSource",
    "SOURCES",
    "get_source",
    "register_source",
]
