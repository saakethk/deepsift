"""
Storage subpackage for disk serialization.
"""
from deepsift.storage.base import Storage
from deepsift.storage.parquet import ParquetStorage

__all__ = [
    "Storage",
    "ParquetStorage",
]
