"""
Generalized Filters class.
Accepts custom filter functions:
    post_filter:    Callable[[Post], bool]
    comment_filter: Callable[[Comment], bool]
Calculates the exact server projection fields needed, preventing unwanted fields
from ever being transmitted over the wire.
"""
from typing import Callable, Optional, Iterable, Union, Set
from scripts.models import Post, Comment, PostField, CommentField


class RequiredFieldError(ValueError):
    """Raised when attempting to exclude a fundamentally required entity field."""
    pass


class Filters:
    """
    Generalized filter container.
    Manages custom predicate functions and minimal server-side field projections.
    """

    def __init__(
        self,
        post_filter: Optional[Callable[[Post], bool]] = None,
        comment_filter: Optional[Callable[[Comment], bool]] = None,
        post_include_fields: Optional[Iterable[Union[str, PostField]]] = None,
        comment_include_fields: Optional[Iterable[Union[str, CommentField]]] = None,
        post_exclude_fields: Optional[Iterable[Union[str, PostField]]] = None,
        comment_exclude_fields: Optional[Iterable[Union[str, CommentField]]] = None,
        additional_filter_fields: Optional[Iterable[Union[str, PostField]]] = None,
        validate: bool = True,
    ):
        self.post_filter = post_filter or (lambda post: True)
        self.comment_filter = comment_filter or (lambda comment: True)

        if validate:
            self.post_include_fields = PostField.validate_many(post_include_fields)
            self.comment_include_fields = CommentField.validate_many(comment_include_fields)
            self.post_exclude_fields = PostField.validate_many(post_exclude_fields)
            self.comment_exclude_fields = CommentField.validate_many(comment_exclude_fields)
            self.additional_filter_fields = PostField.validate_many(additional_filter_fields)
        else:
            self.post_include_fields = {str(f) for f in post_include_fields} if post_include_fields else None
            self.comment_include_fields = {str(f) for f in comment_include_fields} if comment_include_fields else None
            self.post_exclude_fields = {str(f) for f in post_exclude_fields} if post_exclude_fields else None
            self.comment_exclude_fields = {str(f) for f in comment_exclude_fields} if comment_exclude_fields else None
            self.additional_filter_fields = {str(f) for f in additional_filter_fields} if additional_filter_fields else None

        # Always strictly reject exclusion of required schema fields
        self._validate_required(self.post_exclude_fields, Post.REQUIRED_FIELDS, "post_exclude_fields")
        self._validate_required(self.comment_exclude_fields, Comment.REQUIRED_FIELDS, "comment_exclude_fields")

        self.required_post_fields = self._compute_projection(
            self.post_include_fields, self.post_exclude_fields, Post.REQUIRED_FIELDS,
            PostField.all_fields(), self.additional_filter_fields
        )
        self.required_comment_fields = self._compute_projection(
            self.comment_include_fields, self.comment_exclude_fields, Comment.REQUIRED_FIELDS,
            CommentField.all_fields()
        )

    @staticmethod
    def _validate_required(exclude_fields: Optional[Set[str]], required_fields: frozenset, param_name: str):
        if exclude_fields:
            for field in required_fields:
                if field in exclude_fields:
                    raise RequiredFieldError(
                        f"Required field '{field}' cannot be excluded in {param_name}. "
                        f"Required fields: {sorted(list(required_fields))}."
                    )

    @staticmethod
    def _compute_projection(
        include: Optional[Set[str]],
        exclude: Optional[Set[str]],
        required: frozenset,
        all_fields: Set[str],
        extra: Optional[Set[str]] = None,
    ) -> Optional[Set[str]]:
        if include is None and exclude is None:
            return None

        core = set(required)
        if include is not None:
            fields = set(include) | core
            if exclude:
                fields -= (exclude - core)
        else:
            fields = (all_fields - exclude) | core

        if extra:
            fields |= extra
        return fields

    def is_valid_post(self, post: Post) -> bool:
        """Evaluates custom filter against a typed Post object."""
        return bool(self.post_filter(post))

    def is_valid_comment(self, comment: Comment) -> bool:
        """Evaluates custom filter against a typed Comment object."""
        return bool(self.comment_filter(comment))

    def filter_post_record(self, post: Post) -> dict:
        """Serializes post to dict."""
        return post.to_dict()

    def filter_comment_record(self, comment: Comment) -> dict:
        """Serializes comment to dict."""
        return comment.to_dict()
