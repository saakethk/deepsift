"""
Storage subpackage for disk serialization.
"""
from scripts.storage.base import Storage
from scripts.storage.parquet import ParquetStorage

__all__ = [
    "Storage",
    "ParquetStorage",
]
