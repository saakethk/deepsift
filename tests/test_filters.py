import pytest
from scripts.models import Post, Comment
from scripts.filters import Filters, RequiredFieldError


def test_filters_default_projection_and_predicates():
    f = Filters()
    assert f.required_post_fields is None
    assert f.required_comment_fields is None

    post = Post({"id": "p1", "created_utc": 100, "subreddit": "resumes"})
    comment = Comment({"id": "c1", "post_id": "p1", "parent_id": "t3_p1"})

    assert f.is_valid_post(post) is True
    assert f.is_valid_comment(comment) is True


def test_custom_predicates():
    f = Filters(
        post_filter=lambda p: p.score >= 50,
        comment_filter=lambda c: "improve" in c.body.lower(),
    )

    good_post = Post({"id": "p1", "created_utc": 100, "subreddit": "resumes", "score": 75})
    bad_post = Post({"id": "p2", "created_utc": 100, "subreddit": "resumes", "score": 10})
    assert f.is_valid_post(good_post) is True
    assert f.is_valid_post(bad_post) is False

    matching_comment = Comment({
        "id": "c1", "post_id": "p1", "parent_id": "t3_p1", "body": "Improve your action verbs."
    })
    non_matching_comment = Comment({
        "id": "c2", "post_id": "p1", "parent_id": "t3_p1", "body": "Looks good to me."
    })
    assert f.is_valid_comment(matching_comment) is True
    assert f.is_valid_comment(non_matching_comment) is False


def test_required_fields_cannot_be_excluded():
    with pytest.raises(RequiredFieldError) as exc_post_id:
        Filters(post_exclude_fields=["id"])
    assert "Required field 'id' cannot be excluded" in str(exc_post_id.value)

    with pytest.raises(RequiredFieldError) as exc_post_utc:
        Filters(post_exclude_fields=["created_utc"])
    assert "created_utc" in str(exc_post_utc.value)

    with pytest.raises(RequiredFieldError) as exc_comment:
        Filters(comment_exclude_fields=["parent_id"])
    assert "parent_id" in str(exc_comment.value)


def test_required_fields_enforced_even_when_not_in_include_fields():
    f = Filters(post_include_fields=["title", "selftext"])
    assert "title" in f.required_post_fields
    assert "selftext" in f.required_post_fields
    assert "id" in f.required_post_fields
    assert "created_utc" in f.required_post_fields
    assert "subreddit" in f.required_post_fields


def test_field_exclusion_removes_from_all_fields():
    f = Filters(post_exclude_fields=["author_flair_text", "over_18"])
    assert "author_flair_text" not in f.required_post_fields
    assert "over_18" not in f.required_post_fields
    assert "id" in f.required_post_fields
    assert "title" in f.required_post_fields


def test_filters_case_normalization_when_validate_false():
    f = Filters(
        validate=False,
        post_include_fields=["TITLE", "URL "],
        comment_include_fields=["BODY", "AUTHOR"],
    )
    assert "title" in f.post_include_fields
    assert "url" in f.post_include_fields
    assert "body" in f.comment_include_fields
    assert "author" in f.comment_include_fields
