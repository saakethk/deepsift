import copy
import pickle
import pytest
from scripts.models import Post, Comment, PostField, CommentField, UnretrievedFieldError
from scripts.models.base import RedditEntity


def test_post_creation_and_attributes():
    raw = {
        "id": "18abc",
        "created_utc": 1700000000,
        "subreddit": "resumes",
        "title": "Software Engineer Resume Review",
        "score": 42,
    }
    post = Post(raw)
    assert post.id == "18abc"
    assert post.created_utc == 1700000000
    assert post.subreddit == "resumes"
    assert post.title == "Software Engineer Resume Review"
    assert post.score == 42
    assert post.to_dict() == raw


def test_unretrieved_field_error_semantics():
    post = Post({"id": "18abc", "created_utc": 1700000000, "subreddit": "resumes"})

    # Known entity field, but not in payload
    assert not hasattr(post, "selftext")

    with pytest.raises(UnretrievedFieldError) as exc_attr:
        _ = post.selftext
    assert issubclass(UnretrievedFieldError, AttributeError)
    assert "was not retrieved" in str(exc_attr.value)

    with pytest.raises(UnretrievedFieldError) as exc_key:
        _ = post["selftext"]
    assert issubclass(UnretrievedFieldError, KeyError)
    assert "was not retrieved" in str(exc_key.value)


def test_invalid_field_raises_attribute_and_key_errors():
    post = Post({"id": "18abc", "created_utc": 1700000000, "subreddit": "resumes"})

    with pytest.raises(AttributeError):
        _ = post.completely_invalid_field_xyz

    with pytest.raises(KeyError):
        _ = post["completely_invalid_field_xyz"]


def test_private_attribute_guard():
    post = Post({"id": "18abc", "created_utc": 1700000000, "subreddit": "resumes"})
    with pytest.raises(AttributeError):
        _ = post._some_private_var

    # Guard prevents infinite recursion during deepcopy and pickle
    copied = copy.deepcopy(post)
    assert copied.id == post.id

    pickled = pickle.loads(pickle.dumps(post))
    assert pickled.id == post.id


def test_entity_dictionary_mapping_interfaces():
    raw = {"id": "p1", "created_utc": 100, "subreddit": "jobs", "score": 10}
    post = Post(raw)

    assert post["id"] == "p1"
    assert post.get("score") == 10
    assert post.get("unretrieved_known_field", default=99) == 99
    assert post.get("completely_fake_field", default="fallback") == "fallback"

    assert "created_utc" in post
    assert "nonexistent" not in post

    assert len(post) == 4
    assert set(post) == {"id", "created_utc", "subreddit", "score"}
    assert set(post.keys()) == {"id", "created_utc", "subreddit", "score"}
    assert list(post.values()) == ["p1", 100, "jobs", 10]


def test_entity_equality_and_hashing():
    p1 = Post({"id": "post_1", "created_utc": 100, "subreddit": "resumes", "score": 5})
    p2 = Post({"id": "post_1", "created_utc": 100, "subreddit": "resumes", "score": 99})
    p3 = Post({"id": "post_2", "created_utc": 100, "subreddit": "resumes"})

    assert p1 == p2
    assert p1 != p3
    assert hash(p1) == hash(p2)
    assert len({p1, p2, p3}) == 2


def test_comment_attributes_and_is_top_level():
    top_comment = Comment({
        "id": "c1",
        "post_id": "p100",
        "parent_id": "t3_p100",
        "body": "Quantify your achievements.",
    })
    assert top_comment.id == "c1"
    assert top_comment.post_id == "p100"
    assert top_comment.is_top_level is True

    reply_comment = Comment({
        "id": "c2",
        "post_id": "p100",
        "parent_id": "t1_c1",
        "body": "Agreed, use the STAR method.",
    })
    assert reply_comment.is_top_level is False

    sparse_comment = Comment({})
    assert sparse_comment.is_top_level is False


def test_prefix_normalization_ids():
    post = Post({"id": "t3_18abc", "created_utc": 100, "subreddit": "resumes"})
    assert post.id == "18abc"

    comment = Comment({"id": "t1_c999", "post_id": "t3_p888", "parent_id": "t3_p888"})
    assert comment.id == "c999"
    assert comment.post_id == "p888"


def test_field_enums_and_typo_suggestions():
    assert PostField.validate("title") == "title"
    assert PostField.validate("TITLE") == "title"
    assert CommentField.validate("parent_id") == "parent_id"

    with pytest.raises(ValueError) as exc:
        PostField.validate("titel")
    assert "Did you mean 'title'?" in str(exc.value)

    validated = PostField.validate_many(["id", "created_utc"])
    assert validated == {"id", "created_utc"}
