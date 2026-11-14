"""
Abstract base class for storage implementations.
Defines required interface for streaming scraped Reddit records to disk or databases.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any


class Storage(ABC):
    """
    Abstract Base Class for record storage.
    Enforces thread-safe, batch-oriented serialization and resource cleanup.
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.records_written: int = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @abstractmethod
    def write_batch(self, batch: List[Dict[str, Any]]) -> None:
        """
        Writes a batch of record dictionaries to the target storage.
        Implementations should be thread-safe across parallel workers.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Flushes buffers and releases any underlying file or connection handles."""
        pass
