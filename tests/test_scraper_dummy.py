import os
import json
from datetime import datetime, date, timezone
import pytest
from scripts.models import Post, Comment, UnretrievedFieldError
from scripts.filters import Filters
from scripts.sources.dummy import DummySource
from scripts.scraper import RedditScraper, to_utc_datetime


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
