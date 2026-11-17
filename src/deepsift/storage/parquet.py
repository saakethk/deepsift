"""
Parquet streaming writer using PyArrow.
Thread-safe direct-to-disk chunked writer.
"""
import os
import json
import threading
from typing import List, Dict, Any
import pyarrow as pa
import pyarrow.parquet as pq

from deepsift.storage.base import Storage


class ParquetStorage(Storage):
    """
    Direct-to-disk streaming writer for Parquet format.
    Thread-safe across parallel shard workers.
    Handles dynamic column schemas across batches by serializing complex nested values.
    """

    POLYMORPHIC_FIELDS = frozenset({"edited", "author_flair_text", "link_flair_text", "distinguished"})

    def __init__(self, filepath: str):
        super().__init__(filepath)
        self.writer = None
        self.schema = None
        self._closed = False
        self._lock = threading.Lock()

        dir_path = os.path.dirname(os.path.abspath(filepath))
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

    def _sanitize_schema(self, schema: pa.Schema) -> pa.Schema:
        """Promotes null and polymorphic Reddit fields to string to avoid cross-batch type conflicts."""
        fields = []
        for f in schema:
            if pa.types.is_null(f.type) or f.name in self.POLYMORPHIC_FIELDS:
                fields.append(pa.field(f.name, pa.string()))
            else:
                fields.append(f)
        return pa.schema(fields)

    def write_batch(self, batch: List[Dict[str, Any]]):
        if self._closed:
            raise RuntimeError(f"Cannot write to closed ParquetStorage '{self.filepath}'")
        if not batch:
            return

        cleaned_batch = []
        for row in batch:
            clean_row = {}
            for k, v in row.items():
                if isinstance(v, (dict, list)):
                    clean_row[k] = json.dumps(v, default=str)
                elif k in self.POLYMORPHIC_FIELDS and v is not None and not isinstance(v, str):
                    clean_row[k] = str(v)
                else:
                    clean_row[k] = v
            cleaned_batch.append(clean_row)

        with self._lock:
            if self.schema is None:
                initial_table = pa.Table.from_pylist(cleaned_batch)
                self.schema = self._sanitize_schema(initial_table.schema)
                self.writer = pq.ParquetWriter(self.filepath, self.schema, compression="snappy")

            string_cols = {f.name for f in self.schema if pa.types.is_string(f.type)}
            for row in cleaned_batch:
                for col in string_cols:
                    if col in row and row[col] is not None and not isinstance(row[col], str):
                        row[col] = str(row[col])
            table = pa.Table.from_pylist(cleaned_batch, schema=self.schema)

            self.writer.write_table(table)
            self.records_written += len(batch)

    def close(self):
        with self._lock:
            self._closed = True
            if self.writer is not None:
                self.writer.close()
                self.writer = None
            elif self.records_written == 0:
                print(f"[i] Info: Parquet file '{self.filepath}' was not created due to lack of results.")
