"""
Stream batches of Python dictionaries directly into a single Parquet file on disk.
Unifies all columns across all records and preserves complex/nested structures via JSON encoding.
"""
import os
import json
import threading
import pandas as pd


class ParquetStreamer:
    """Streams and unifies all fields from records into a Parquet file on disk."""

    def __init__(self, filepath: str, compression: str = "zstd"):
        self.filepath = filepath
        self.compression = compression
        self.records = []
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    def write_batch(self, records: list[dict]):
        if not records:
            return
        with self._lock:
            self.records.extend(records)

    def close(self):
        with self._lock:
            if not self.records:
                return

            # Sanitize complex/nested structures (dicts, lists) to JSON strings
            sanitized = []
            for r in self.records:
                clean = {}
                for k, v in r.items():
                    clean[k] = json.dumps(v) if isinstance(v, (dict, list)) else v
                sanitized.append(clean)

            # Convert to DataFrame with automatic schema outer-join
            df = pd.DataFrame(sanitized)
            df.to_parquet(self.filepath, compression=self.compression, engine="pyarrow")
            self.records = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
