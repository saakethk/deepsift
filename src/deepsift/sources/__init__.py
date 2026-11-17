"""
Data sources subpackage for Reddit scraping.
"""
from deepsift.sources.base import Source
from deepsift.sources.arctic_shift import ArcticShiftSource
from deepsift.sources.registry import SOURCES, get_source, register_source

__all__ = [
    "Source",
    "ArcticShiftSource",
    "SOURCES",
    "get_source",
    "register_source",
]
