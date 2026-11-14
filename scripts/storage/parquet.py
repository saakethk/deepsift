"""
Parquet streaming writer using PyArrow.
Thread-safe direct-to-disk chunked writer.
"""
import json
import threading
import pyarrow as pa
import pyarrow.parquet as pq


class ParquetStreamer:
    """
    Direct-to-disk streaming writer for Parquet format.
    Thread-safe across parallel shard workers.
    Handles dynamic column schemas across batches by serializing complex nested values.
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.writer = None
        self.schema = None
        self.records_written = 0
        self._lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def write_batch(self, batch: list[dict]):
        if not batch:
            return

        cleaned_batch = []
        for row in batch:
            clean_row = {}
            for k, v in row.items():
                if isinstance(v, (dict, list)):
                    clean_row[k] = json.dumps(v)
                elif v is not None:
                    clean_row[k] = v
            cleaned_batch.append(clean_row)

        table = pa.Table.from_pylist(cleaned_batch, schema=self.schema)
        with self._lock:
            if self.writer is None:
                self.schema = table.schema
                self.writer = pq.ParquetWriter(self.filepath, self.schema, compression="snappy")

            self.writer.write_table(table)
            self.records_written += len(batch)

    def close(self):
        with self._lock:
            if self.writer is not None:
                self.writer.close()
                self.writer = None
