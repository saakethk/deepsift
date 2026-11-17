import os
import json
from datetime import datetime, date, timezone
import pytest
from deepsift.models import Post, Comment, UnretrievedFieldError
from deepsift.filters import Filters
from deepsift.sources.dummy import DummySource
from deepsift.scraper import RedditScraper, to_utc_datetime


def test_to_utc_datetime_normalization():
    # Datetime object with and without tzinfo
    dt_naive = datetime(2024, 1, 15, 12, 0)
    assert to_utc_datetime(dt_naive) == datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)

    # Date object
    d = date(2024, 5, 20)
    assert to_utc_datetime(d) == datetime(2024, 5, 20, 0, 0, tzinfo=timezone.utc)

    # Numeric timestamp
    assert to_utc_datetime(1700000000) == datetime.fromtimestamp(1700000000, tz=timezone.utc)

    # String numeric timestamp
    assert to_utc_datetime("1700000000") == datetime.fromtimestamp(1700000000, tz=timezone.utc)

    # ISO strings
    assert to_utc_datetime("2024-01-01T00:00:00Z") == datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert to_utc_datetime("2024-01-01") == datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)

    # Invalid input
    with pytest.raises(TypeError):
        to_utc_datetime([])


def test_scraper_parameter_validation():
    with pytest.raises(ValueError):
        RedditScraper(shard_days=0)
    with pytest.raises(ValueError):
        RedditScraper(post_workers=0)
    with pytest.raises(ValueError):
        RedditScraper(comment_workers=-1)


def test_full_pipeline_run_dummy_source(tmp_path):
    posts_out = str(tmp_path / "posts.parquet")
    comments_out = str(tmp_path / "comments.parquet")
    errors_out = str(tmp_path / "errors.json")

    dummy = DummySource(posts_per_shard=15, comments_per_post=2, match_ratio=1.0)
    scraper = RedditScraper(source=dummy, shard_days=30, post_workers=2, comment_workers=2)

    posts, comments = scraper.run(
        subreddits=["resumes"],
        from_dt="2024-01-01",
        to_dt="2024-02-15",
        posts_output=posts_out,
        comments_output=comments_out,
        errors_output=errors_out,
    )

    assert len(posts) > 0
    assert comments > 0
    assert os.path.exists(posts_out)
    assert os.path.exists(comments_out)
    # Clean run produces no errors.json
    assert not os.path.exists(errors_out)


def test_filtered_posts_and_comments_pipeline(tmp_path):
    posts_out = str(tmp_path / "filtered_posts.parquet")
    comments_out = str(tmp_path / "filtered_comments.parquet")

    # Filter posts with score >= 100
    filters = Filters(
        post_filter=lambda p: p.score >= 100,
        comment_filter=lambda c: len(c.body) > 10,
    )

    dummy = DummySource(posts_per_shard=20, comments_per_post=3)
    scraper = RedditScraper(filters=filters, source=dummy, shard_days=30)

    posts, comments = scraper.run(
        subreddits=["resumes"],
        from_dt="2024-01-01",
        to_dt="2024-02-01",
        posts_output=posts_out,
        comments_output=comments_out,
    )

    assert os.path.exists(posts_out)
    import pyarrow.parquet as pq
    table = pq.read_table(posts_out)
    scores = table.column("score").to_pylist()
    assert all(s >= 100 for s in scores)


def test_errors_log_when_partial_failures_occur(tmp_path, capsys):
    posts_out = str(tmp_path / "posts.parquet")
    comments_out = str(tmp_path / "comments.parquet")
    errors_out = str(tmp_path / "errors.json")

    dummy = DummySource(posts_per_shard=5, comments_per_post=2)
    scraper = RedditScraper(source=dummy, shard_days=10)

    # Inject a recorded error
    scraper.errors.append({
        "stage": "post_shard",
        "subreddit": "resumes",
        "error_type": "TransientNetworkTimeout",
        "error_message": "Read timeout during shard scan",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    posts, comments = scraper.run(
        subreddits=["resumes"],
        from_dt="2024-01-01",
        to_dt="2024-01-10",
        posts_output=posts_out,
        comments_output=comments_out,
        errors_output=errors_out,
    )

    assert os.path.exists(errors_out)
    with open(errors_out) as f:
        data = json.load(f)

    assert data["status"] == "completed_with_errors"
    assert data["summary"]["total_errors"] == 1
    assert data["execution"]["source"] == "dummy"
    assert data["execution"]["duration_seconds"] >= 0
    assert data["succeeded"]["posts_count"] == len(posts)
    assert data["succeeded"]["comments_count"] == comments

    captured = capsys.readouterr()
    assert "1 error(s) occurred during execution" in captured.out
    assert errors_out in captured.out


def test_fatal_error_logs_and_re_raises(tmp_path, capsys):
    errors_out = str(tmp_path / "fatal_errors.json")
    scraper = RedditScraper()

    # from_dt after to_dt will cause ValueError
    with pytest.raises(ValueError) as exc:
        scraper.run(
            subreddits=["resumes"],
            from_dt="2024-02-01",
            to_dt="2024-01-01",
            errors_output=errors_out,
        )
    assert "must precede" in str(exc.value)

    assert os.path.exists(errors_out)
    with open(errors_out) as f:
        data = json.load(f)

    assert data["status"] == "failed"
    assert data["failures"][0]["error_type"] == "ValueError"

    captured = capsys.readouterr()
    assert "error(s) occurred during execution" in captured.out


def test_unretrieved_field_in_filter_logs_descriptive_error(tmp_path):
    posts_out = str(tmp_path / "posts.parquet")
    errors_out = str(tmp_path / "errors.json")

    # Filter accesses 'title', but projection strictly requests only 'id' and 'created_utc'
    filters = Filters(
        post_filter=lambda p: p.title == "Target",
        post_include_fields=["id", "created_utc"],
    )
    dummy = DummySource(posts_per_shard=5)
    scraper = RedditScraper(filters=filters, source=dummy)

    scraper.scrape_posts(
        subreddits="resumes",
        from_dt="2024-01-01",
        to_dt="2024-01-10",
        output_path=posts_out,
        errors_output=errors_out,
    )

    assert len(scraper.errors) == 1
    assert scraper.errors[0]["error_type"] == "UnretrievedFieldError"
    assert "title" in scraper.errors[0]["error_message"]


def test_empty_subreddits_raises_value_error(tmp_path):
    errors_out = str(tmp_path / "errors.json")
    scraper = RedditScraper()
    with pytest.raises(ValueError) as exc:
        scraper.run(subreddits=[], from_dt="2024-01-01", errors_output=errors_out)
    assert "At least one subreddit must be specified" in str(exc.value)


def test_pipeline_determinism_multiple_runs(tmp_path):
    import pyarrow.parquet as pq

    run1_posts = str(tmp_path / "run1_posts.parquet")
    run1_comments = str(tmp_path / "run1_comments.parquet")
    run2_posts = str(tmp_path / "run2_posts.parquet")
    run2_comments = str(tmp_path / "run2_comments.parquet")

    filters = Filters(
        post_filter=lambda p: p.score >= 10,
        comment_filter=lambda c: len(c.body) > 5,
        post_include_fields=["id", "title", "score", "author", "created_utc"],
        comment_include_fields=["id", "post_id", "parent_id", "body", "score"],
    )

    scraper1 = RedditScraper(
        filters=filters,
        source=DummySource(seed=12345, posts_per_shard=25, comments_per_post=4),
        shard_days=15,
        post_workers=2,
        comment_workers=2,
    )
    posts1, comments_count1 = scraper1.run(
        subreddits=["resumes"],
        from_dt="2024-01-01",
        to_dt="2024-02-15",
        posts_output=run1_posts,
        comments_output=run1_comments,
    )

    scraper2 = RedditScraper(
        filters=filters,
        source=DummySource(seed=12345, posts_per_shard=25, comments_per_post=4),
        shard_days=15,
        post_workers=2,
        comment_workers=2,
    )
    posts2, comments_count2 = scraper2.run(
        subreddits=["resumes"],
        from_dt="2024-01-01",
        to_dt="2024-02-15",
        posts_output=run2_posts,
        comments_output=run2_comments,
    )

    assert set(posts1) == set(posts2)
    assert len(posts1) == len(posts2)
    assert comments_count1 == comments_count2

    table1_posts = sorted(pq.read_table(run1_posts).to_pylist(), key=lambda r: r["id"])
    table2_posts = sorted(pq.read_table(run2_posts).to_pylist(), key=lambda r: r["id"])
    assert table1_posts == table2_posts

    table1_comments = sorted(pq.read_table(run1_comments).to_pylist(), key=lambda r: r["id"])
    table2_comments = sorted(pq.read_table(run2_comments).to_pylist(), key=lambda r: r["id"])
    assert table1_comments == table2_comments


def test_dummy_source_custom_shard_counts(tmp_path):
    posts_out = str(tmp_path / "custom_posts.parquet")
    from_ts = 1704067200
    to_ts = 1704240000

    scraper = RedditScraper(shard_days=1)
    shards, _, _ = scraper._generate_shards(from_ts, to_ts)
    shard_counts = {shards[0]: 14, shards[1]: 28}

    dummy = DummySource(posts_per_shard=shard_counts, match_ratio=1.0)
    scraper.source = dummy

    posts = scraper.scrape_posts(
        subreddits=["resumes"],
        from_dt=from_ts,
        to_dt=to_ts,
        output_path=posts_out,
    )
    assert len(posts) == 14 + 28


def test_unpack_nodes_filters_more_stubs():
    from deepsift.sources.arctic_shift import ArcticShiftSource
    source = ArcticShiftSource()

    mock_tree = [
        {
            "kind": "t1",
            "data": {
                "id": "c101",
                "parent_id": "t3_post1",
                "body": "This is a real comment",
                "score": 10,
                "replies": {
                    "data": {
                        "children": [
                            {
                                "kind": "more",
                                "data": {
                                    "count": 5,
                                    "name": "t1_c102",
                                    "id": "c102",
                                    "parent_id": "t1_c101",
                                    "depth": 2,
                                    "children": ["c103", "c104"],
                                },
                            }
                        ]
                    }
                },
            },
        },
        {
            "kind": "more",
            "data": {
                "count": 3,
                "name": "t1_top_more",
                "id": "top_more",
                "parent_id": "t3_post1",
                "children": ["c105"],
            },
        },
    ]

    unpacked = source._unpack_nodes(mock_tree, "post1")
    assert len(unpacked) == 1
    assert unpacked[0]["id"] == "c101"
    assert unpacked[0]["body"] == "This is a real comment"
    assert unpacked[0]["post_id"] == "post1"


