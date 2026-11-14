"""
Live integration tests using the actual Arctic Shift API.
Verifies network fetching, server-side field projection, comment tree resolution,
and Parquet disk serialization against real Reddit data.
"""
import asyncio
import tempfile
from pathlib import Path
import pytest
import httpx
import pyarrow.parquet as pq
from click.testing import CliRunner

from deepsift.sources.arctic_shift import ArcticShiftSource
from deepsift.models import PostField, CommentField, Post, Comment
from deepsift.filters import Filters
from deepsift.scraper import RedditScraper
from deepsift.cli import cli

pytestmark = pytest.mark.live


def test_live_fetch_posts_shard_projection_and_timestamps():
    source = ArcticShiftSource(batch_size=50)
    after_ts = 1704150000
    before_ts = 1704153600
    requested_fields = [PostField.ID, PostField.TITLE, PostField.SCORE, PostField.NUM_COMMENTS]

    shards = list(source.fetch_posts_shard(
        subreddit="resumes",
        after_ts=after_ts,
        before_ts=before_ts,
        fields=requested_fields
    ))

    assert len(shards) > 0
    all_posts = [p for batch in shards for p in batch]
    assert len(all_posts) > 0

    for raw_post in all_posts:
        post = Post.from_api_dict(raw_post)
        assert post.id
        assert post.created_utc >= after_ts
        assert post.created_utc <= before_ts
        assert post.subreddit.lower() == "resumes"
        assert post.title is not None
        assert "selftext" not in raw_post


@pytest.mark.anyio
async def test_live_fetch_comments_for_post():
    source = ArcticShiftSource()
    known_post_id = "1xwbx95"

    async with httpx.AsyncClient() as client:
        clean_id, raw_comments, success = await source.fetch_comments_for_post(
            client=client,
            post_id=known_post_id,
            fields=[CommentField.ID, CommentField.POST_ID, CommentField.PARENT_ID, CommentField.BODY, CommentField.SCORE]
        )

    assert clean_id == known_post_id
    assert success is True
    assert isinstance(raw_comments, list)
    assert len(raw_comments) > 0

    first_comment = Comment(raw_comments[0], clean_id)
    assert first_comment.id
    assert first_comment.post_id == known_post_id
    assert first_comment.parent_id
    assert first_comment.body is not None


def test_live_scraper_full_pipeline():
    with tempfile.TemporaryDirectory() as tmpdir:
        posts_path = str(Path(tmpdir) / "posts.parquet")
        comments_path = str(Path(tmpdir) / "comments.parquet")
        errors_path = str(Path(tmpdir) / "errors.json")

        filters = Filters(
            post_filter=lambda p: p.score is not None and p.score >= 0,
            post_include_fields=[PostField.ID, PostField.TITLE, PostField.SCORE, PostField.NUM_COMMENTS],
            comment_include_fields=[CommentField.ID, CommentField.POST_ID, CommentField.BODY, CommentField.SCORE, CommentField.EDITED]
        )

        scraper = RedditScraper(
            filters=filters,
            source=ArcticShiftSource(),
            shard_days=1,
            post_workers=2,
            comment_workers=2,
        )

        posts, comments_count = scraper.run(
            subreddits=["resumes"],
            from_dt=1704150000,
            to_dt=1704153600,
            posts_output=posts_path,
            comments_output=comments_path,
            errors_output=errors_path,
        )

        assert len(posts) > 0
        assert Path(posts_path).exists()
        post_table = pq.read_table(posts_path)
        assert len(post_table) == len(posts)
        assert "id" in post_table.column_names
        assert "title" in post_table.column_names

        if comments_count > 0:
            assert Path(comments_path).exists()
            comment_table = pq.read_table(comments_path)
            assert len(comment_table) == comments_count
            assert "id" in comment_table.column_names
            assert "post_id" in comment_table.column_names


def test_live_empty_time_window_returns_cleanly():
    with tempfile.TemporaryDirectory() as tmpdir:
        posts_path = str(Path(tmpdir) / "empty_posts.parquet")
        scraper = RedditScraper(shard_days=1)

        posts = scraper.scrape_posts(
            subreddits=["resumes"],
            from_dt=1000000000,
            to_dt=1000000010,
            output_path=posts_path,
        )

        assert posts == []
        assert not Path(posts_path).exists()


@pytest.mark.anyio
async def test_live_invalid_post_comments_handling():
    source = ArcticShiftSource()
    fake_post_id = "000000"

    async with httpx.AsyncClient() as client:
        clean_id, comments, success = await source.fetch_comments_for_post(
            client=client,
            post_id=fake_post_id
        )

    assert clean_id == fake_post_id
    assert comments == []


def test_live_cli_execution():
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        posts_path = str(Path(tmpdir) / "cli_posts.parquet")
        result = runner.invoke(cli, [
            "posts",
            "--subreddits", "resumes",
            "--from", "1704150000",
            "--to", "1704153600",
            "--output", posts_path,
            "--include-fields", "id",
            "--include-fields", "title",
            "--include-fields", "score",
            "--shard-days", "1",
        ])

        assert result.exit_code == 0
        assert Path(posts_path).exists()
        table = pq.read_table(posts_path)
        assert len(table) > 0


def test_live_determinism_historical_data():
    source = ArcticShiftSource(batch_size=20)
    after_ts = 1704150000
    before_ts = 1704153600
    fields = [PostField.ID, PostField.TITLE, PostField.SCORE, PostField.NUM_COMMENTS]

    shards1 = list(source.fetch_posts_shard(
        subreddit="resumes",
        after_ts=after_ts,
        before_ts=before_ts,
        fields=fields,
    ))
    posts1 = [p for batch in shards1 for p in batch]

    shards2 = list(source.fetch_posts_shard(
        subreddit="resumes",
        after_ts=after_ts,
        before_ts=before_ts,
        fields=fields,
    ))
    posts2 = [p for batch in shards2 for p in batch]

    assert len(posts1) > 0
    assert len(posts1) == len(posts2)
    assert [p["id"] for p in posts1] == [p["id"] for p in posts2]
    assert posts1 == posts2
