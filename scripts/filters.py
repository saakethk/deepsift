"""
Generalized Filters class.
Accepts custom filter functions:
    post_filter:    Callable[[Post], bool]
    comment_filter: Callable[[Comment], bool]
Calculates the exact server projection fields needed, so the server never transmits
unwanted/excluded fields over the wire.
Validates column restrictions against PostField and CommentField enumerations.
Inspects filter function parameter types and accessed fields to raise errors upfront
if filters attempt to access unretrieved or excluded fields.
"""
import dis
from typing import Callable, Optional, Iterable, Union, Set, get_type_hints
from scripts.models import Post, Comment, PostField, CommentField, RedditEntity, UnretrievedFieldError


def resume_cohort_post_filter(post: Post) -> bool:
    """Standard cohort post filter: score > 0, num_comments > 10, post links to an image."""
    return post.score > 0 and post.num_comments > 10 and post.has_image


def inspect_filter(func: Optional[Callable], expected_cls: type) -> Set[str]:
    """
    Inspects a filter function's parameter types and bytecode.
    Validates that the parameter type matches expected_cls (Post or Comment).
    Extracts all entity fields accessed by the function.
    """
    if func is None or not callable(func):
        return set()

    # Validate type hints if provided
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = getattr(func, "__annotations__", {})

    for param_name, annotated_type in hints.items():
        if param_name != "return":
            if isinstance(annotated_type, type) and issubclass(annotated_type, RedditEntity):
                if annotated_type != expected_cls:
                    raise TypeError(
                        f"Filter parameter '{param_name}' is typed as {annotated_type.__name__}, "
                        f"but expected {expected_cls.__name__}."
                    )

    if not hasattr(func, "__code__"):
        return set()

    first_arg = func.__code__.co_varnames[0] if func.__code__.co_argcount > 0 else None
    if not first_arg:
        return set()

    accessed = set()
    instructions = list(dis.get_instructions(func))
    for i, inst in enumerate(instructions):
        if inst.opname == "LOAD_FAST" and inst.argval == first_arg:
            if i + 1 < len(instructions):
                next1 = instructions[i + 1]
                if next1.opname in ("LOAD_ATTR", "LOAD_METHOD") and next1.argval not in ("get",):
                    accessed.add(next1.argval)
                elif next1.opname in ("LOAD_ATTR", "LOAD_METHOD") and next1.argval == "get":
                    if i + 2 < len(instructions) and instructions[i + 2].opname == "LOAD_CONST":
                        if isinstance(instructions[i + 2].argval, str):
                            accessed.add(instructions[i + 2].argval)
                elif next1.opname == "LOAD_CONST" and i + 2 < len(instructions) and instructions[i + 2].opname == "BINARY_SUBSCR":
                    if isinstance(next1.argval, str):
                        accessed.add(next1.argval)

    # Resolve properties to underlying API fields
    resolved = set()
    for attr in accessed:
        if attr.startswith("_"):
            continue
        if attr == "has_image":
            resolved.add("url")
        elif attr == "is_top_level":
            resolved.add("parent_id")
        else:
            resolved.add(attr)
    return resolved


class Filters:
    """
    Generalized filter container.
    Users can define:
    Row logic: custom post_filter and comment_filter functions taking typed Post / Comment objects.
    Column selection: what is important (include_fields) vs unimportant (exclude_fields),
    validated strictly against PostField and CommentField enumerations.
    Server Projection: automatically calculates the minimal set of fields to request from the API,
    preventing excluded/unimportant fields from ever being transmitted from the server.
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
        # Extra fields required by custom filter predicates (if not already in include_fields)
        additional_filter_fields: Optional[Iterable[Union[str, PostField]]] = None,
        validate: bool = True,
    ):
        self.post_filter = post_filter or (lambda post: True)
        self.comment_filter = comment_filter or (lambda comment: True)

        self._post_filter_fields = inspect_filter(self.post_filter, Post)
        self._comment_filter_fields = inspect_filter(self.comment_filter, Comment)

        if validate:
            self.post_include_fields = PostField.validate_many(post_include_fields)
            self.comment_include_fields = CommentField.validate_many(comment_include_fields)
            self.post_exclude_fields = PostField.validate_many(post_exclude_fields)
            self.comment_exclude_fields = CommentField.validate_many(comment_exclude_fields)
            self.additional_filter_fields = PostField.validate_many(additional_filter_fields)

            # Validate that fundamentally required fields are not excluded
            if self.post_exclude_fields:
                for req_field in Post.REQUIRED_FIELDS:
                    if req_field in self.post_exclude_fields:
                        raise ValueError(
                            f"Required field '{req_field}' cannot be excluded in post_exclude_fields."
                        )

            if self.comment_exclude_fields:
                for req_field in Comment.REQUIRED_FIELDS:
                    if req_field in self.comment_exclude_fields:
                        raise ValueError(
                            f"Required field '{req_field}' cannot be excluded in comment_exclude_fields."
                        )

            # Validate that filter functions do not access excluded fields
            if self.post_exclude_fields:
                for field in self._post_filter_fields:
                    if field in self.post_exclude_fields:
                        raise ValueError(
                            f"Field '{field}' cannot be excluded in post_exclude_fields because post_filter requires it."
                        )

            if self.comment_exclude_fields:
                for field in self._comment_filter_fields:
                    if field in self.comment_exclude_fields:
                        raise ValueError(
                            f"Field '{field}' cannot be excluded in comment_exclude_fields because comment_filter requires it."
                        )

            # Validate that filter functions do not access unretrieved fields
            if self.post_include_fields is not None:
                for field in self._post_filter_fields:
                    if field not in self.post_include_fields:
                        raise UnretrievedFieldError(
                            f"post_filter accesses field '{field}', but '{field}' is not in post_include_fields "
                            f"({sorted(list(self.post_include_fields))}). Only fields expected to be retrieved can be accessed."
                        )

            if self.comment_include_fields is not None:
                for field in self._comment_filter_fields:
                    if field not in self.comment_include_fields:
                        raise UnretrievedFieldError(
                            f"comment_filter accesses field '{field}', but '{field}' is not in comment_include_fields "
                            f"({sorted(list(self.comment_include_fields))}). Only fields expected to be retrieved can be accessed."
                        )
        else:
            self.post_include_fields = {str(f) for f in post_include_fields} if post_include_fields else None
            self.comment_include_fields = {str(f) for f in comment_include_fields} if comment_include_fields else None
            self.post_exclude_fields = {str(f) for f in post_exclude_fields} if post_exclude_fields else None
            self.comment_exclude_fields = {str(f) for f in comment_exclude_fields} if comment_exclude_fields else None
            self.additional_filter_fields = {str(f) for f in additional_filter_fields} if additional_filter_fields else None

        # Pre-calculate minimal projection fields for server queries
        self.required_post_fields: Optional[Set[str]] = self._calculate_required_post_fields()
        self.required_comment_fields: Optional[Set[str]] = self._calculate_required_comment_fields()

    def _calculate_required_post_fields(self) -> Optional[Set[str]]:
        """
        Calculates minimal field set required from the server.
        Returns None if user wants 100% of raw fields (no include or exclude specified).
        """
        if self.post_include_fields is None and self.post_exclude_fields is None:
            return None

        # Core fields needed for pagination, hierarchy, and filter predicates
        core_fields = set(Post.REQUIRED_FIELDS) | self._post_filter_fields

        if self.post_include_fields is not None:
            fields = set(self.post_include_fields) | core_fields
            if self.post_exclude_fields:
                fields -= (self.post_exclude_fields - set(Post.REQUIRED_FIELDS))
        else:
            fields = PostField.all_fields() - self.post_exclude_fields
            fields |= core_fields

        if self.additional_filter_fields:
            fields |= self.additional_filter_fields

        return fields

    def _calculate_required_comment_fields(self) -> Optional[Set[str]]:
        """Calculates minimal comment fields required from the server."""
        if self.comment_include_fields is None and self.comment_exclude_fields is None:
            return None

        # Core fields needed for pagination, hierarchy, and filter predicates
        core_fields = set(Comment.REQUIRED_FIELDS) | self._comment_filter_fields

        if self.comment_include_fields is not None:
            fields = set(self.comment_include_fields) | core_fields
            if self.comment_exclude_fields:
                fields -= (self.comment_exclude_fields - set(Comment.REQUIRED_FIELDS))
        else:
            fields = CommentField.all_fields() - self.comment_exclude_fields
            fields |= core_fields

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
