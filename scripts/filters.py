"""
Generalized Filters class.
Accepts custom filter functions:
    post_filter:    Callable[[Post], bool]
    comment_filter: Callable[[Comment], bool]
Validates column restrictions against PostField and CommentField enumerations
so users can specify what is important (include_fields) and what is not important (exclude_fields).
"""
from typing import Callable, Optional, Iterable, Union, Set
from scripts.enums import PostField, CommentField
from scripts.models import Post, Comment


def resume_cohort_post_filter(post: Post) -> bool:
    """Standard cohort post filter: score > 0, num_comments > 10, URL is an image."""
    return post.score > 0 and post.num_comments > 10 and post.is_image


def default_comment_filter(comment: Comment) -> bool:
    """Standard comment filter: excludes AutoModerator and blank bodies."""
    return not comment.is_automod and bool(comment.body.strip())


class Filters:
    """
    Generalized filter container.
    Users can define:
    1. Row logic: custom post_filter and comment_filter functions taking typed Post / Comment objects.
    2. Column selection: what is important (include_fields) vs unimportant (exclude_fields),
       validated strictly against PostField and CommentField enumerations.
    """

    def __init__(
        self,
        post_filter: Optional[Callable[[Post], bool]] = None,
        comment_filter: Optional[Callable[[Comment], bool]] = None,
        # Column selection (what is important to keep)
        post_include_fields: Optional[Iterable[Union[str, PostField]]] = None,
        comment_include_fields: Optional[Iterable[Union[str, CommentField]]] = None,
        # Column removal (what is not important / noise to drop)
        post_exclude_fields: Optional[Iterable[Union[str, PostField]]] = None,
        comment_exclude_fields: Optional[Iterable[Union[str, CommentField]]] = None,
        validate: bool = True,
    ):
        self.post_filter = post_filter or (lambda post: True)
        self.comment_filter = comment_filter or (lambda comment: True)

        if validate:
            self.post_include_fields = PostField.validate_many(post_include_fields)
            self.comment_include_fields = CommentField.validate_many(comment_include_fields)
            self.post_exclude_fields = PostField.validate_many(post_exclude_fields)
            self.comment_exclude_fields = CommentField.validate_many(comment_exclude_fields)
        else:
            self.post_include_fields = {str(f) for f in post_include_fields} if post_include_fields else None
            self.comment_include_fields = {str(f) for f in comment_include_fields} if comment_include_fields else None
            self.post_exclude_fields = {str(f) for f in post_exclude_fields} if post_exclude_fields else None
            self.comment_exclude_fields = {str(f) for f in comment_exclude_fields} if comment_exclude_fields else None

    def is_valid_post(self, post: Post) -> bool:
        """Evaluates custom filter against a typed Post object."""
        return bool(self.post_filter(post))

    def is_valid_comment(self, comment: Comment) -> bool:
        """Evaluates custom filter against a typed Comment object."""
        return bool(self.comment_filter(comment))

    def filter_post_record(self, post: Post) -> dict:
        """Serializes post to dict, retaining only the fields deemed important."""
        return post.to_dict(
            include_fields=self.post_include_fields,
            exclude_fields=self.post_exclude_fields,
        )

    def filter_comment_record(self, comment: Comment) -> dict:
        """Serializes comment to dict, retaining only the fields deemed important."""
        return comment.to_dict(
            include_fields=self.comment_include_fields,
            exclude_fields=self.comment_exclude_fields,
        )
