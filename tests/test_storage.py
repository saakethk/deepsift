import os
from datetime import datetime
import pyarrow.parquet as pq
from deepsift.storage import ParquetStorage


def test_parquet_storage_write_and_read(tmp_path):
    fpath = str(tmp_path / "test.parquet")
    records = [
        {"id": "p1", "score": 10, "title": "First"},
        {"id": "p2", "score": 20, "title": "Second"},
    ]

    with ParquetStorage(fpath) as storage:
        storage.write_batch(records)
        assert storage.records_written == 2

    table = pq.read_table(fpath)
    assert len(table) == 2
    assert table.column("id").to_pylist() == ["p1", "p2"]
    assert table.column("score").to_pylist() == [10, 20]


def test_parquet_cross_batch_polymorphic_coercion(tmp_path):
    fpath = str(tmp_path / "polymorphic.parquet")

    with ParquetStorage(fpath) as storage:
        # Batch 1: edited is boolean False
        storage.write_batch([{"id": "p1", "edited": False, "score": 100}])
        # Batch 2: edited is an integer Unix timestamp
        storage.write_batch([{"id": "p2", "edited": 1672531199, "score": 200}])
        # Batch 3: edited is an ISO string date
        storage.write_batch([{"id": "p3", "edited": "2024-01-01", "score": 300}])

    table = pq.read_table(fpath)
    assert len(table) == 3
    assert table.column("edited").to_pylist() == ["False", "1672531199", "2024-01-01"]


def test_parquet_null_promotion_across_batches(tmp_path):
    fpath = str(tmp_path / "nulls.parquet")

    with ParquetStorage(fpath) as storage:
        # Batch 1: custom_field is null in all rows
        storage.write_batch([{"id": "p1", "custom_field": None}])
        # Batch 2: custom_field contains string data
        storage.write_batch([{"id": "p2", "custom_field": "valuable_data"}])

    table = pq.read_table(fpath)
    assert len(table) == 2
    assert table.column("custom_field").to_pylist() == [None, "valuable_data"]


def test_parquet_nested_unserializable_objects(tmp_path):
    fpath = str(tmp_path / "nested.parquet")

    with ParquetStorage(fpath) as storage:
        storage.write_batch([
            {
                "id": "p1",
                "tags": {"python", "data"},
                "metadata": {"created": datetime(2024, 1, 1)},
            }
        ])

    table = pq.read_table(fpath)
    assert len(table) == 1
    tags_val = table.column("tags").to_pylist()[0]
    assert "python" in tags_val
    assert "data" in tags_val


def test_parquet_zero_records_creates_no_file(tmp_path, capsys):
    fpath = str(tmp_path / "empty.parquet")

    with ParquetStorage(fpath) as storage:
        storage.write_batch([])
        assert storage.records_written == 0

    assert not os.path.exists(fpath)
    captured = capsys.readouterr()
    assert "was not created due to lack of results" in captured.out


def test_write_to_closed_storage_raises(tmp_path):
    fpath = str(tmp_path / "closed.parquet")
    storage = ParquetStorage(fpath)
    storage.close()

    import pytest
    with pytest.raises(RuntimeError) as exc:
        storage.write_batch([{"id": "p1"}])
    assert "Cannot write to closed ParquetStorage" in str(exc.value)
