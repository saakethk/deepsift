"""
Parquet streaming writer using PyArrow.
Thread-safe direct-to-disk chunked writer.
"""
import os
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

        dir_path = os.path.dirname(os.path.abspath(filepath))
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _sanitize_schema(self, schema: pa.Schema) -> pa.Schema:
        """Promotes any untyped null fields to string to avoid subsequent batch type conflicts."""
        fields = []
        for f in schema:
            if pa.types.is_null(f.type):
                fields.append(pa.field(f.name, pa.string()))
            else:
                fields.append(f)
        return pa.schema(fields)

    def write_batch(self, batch: list[dict]):
        if not batch:
            return

        cleaned_batch = []
        for row in batch:
            clean_row = {}
            for k, v in row.items():
                if isinstance(v, (dict, list)):
                    clean_row[k] = json.dumps(v)
                else:
                    clean_row[k] = v
            cleaned_batch.append(clean_row)

        with self._lock:
            if self.schema is None:
                initial_table = pa.Table.from_pylist(cleaned_batch)
                self.schema = self._sanitize_schema(initial_table.schema)
                self.writer = pq.ParquetWriter(self.filepath, self.schema, compression="snappy")

            table = pa.Table.from_pylist(cleaned_batch, schema=self.schema)
            self.writer.write_table(table)
            self.records_written += len(batch)

    def close(self):
        with self._lock:
            if self.writer is not None:
                self.writer.close()
                self.writer = None
