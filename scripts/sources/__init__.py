"""
Data sources subpackage for Reddit scraping.
"""
from scripts.sources.base import Source
from scripts.sources.arctic_shift import ArcticShiftSource
from scripts.sources.registry import SOURCES, get_source, register_source

__all__ = [
    "Source",
    "ArcticShiftSource",
    "SOURCES",
    "get_source",
    "register_source",
]
