"""
Stream batches of Python dictionaries directly into a single Parquet file on disk.
Keeps RAM usage minimal and protects against data loss during long scraping runs.
"""
import os
import threading
import pyarrow as pa
import pyarrow.parquet as pq


class ParquetStreamer:
    def __init__(self, filepath: str, compression: str = "zstd"):
        self.filepath = filepath
        self.compression = compression
        self.writer = None
        self.schema = None
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    def write_batch(self, records: list[dict]):
        """Writes a batch of records as a row group to the Parquet file."""
        if not records:
            return

        with self._lock:
            table = pa.Table.from_pylist(records, schema=self.schema)
            if self.writer is None:
                self.schema = table.schema
                self.writer = pq.ParquetWriter(
                    self.filepath, self.schema, compression=self.compression
                )
            self.writer.write_table(table)

    def close(self):
        """Closes the Parquet writer if open."""
        with self._lock:
            if self.writer is not None:
                self.writer.close()
                self.writer = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

# Alias for backwards compatibility
ParquetStreamWriter = ParquetStreamer
