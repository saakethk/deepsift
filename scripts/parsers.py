"""
Data transformation functions that convert raw Arctic Shift JSON into validated Post and Comment objects.
"""
from typing import Optional, List
from scripts.models import Post, Comment
from scripts.filters import Filters


def clean_post(post_dict: dict, filters: Optional[Filters] = None) -> dict:
    """Validates raw post dictionary through Post class and returns standardized dict."""
    post = Post.from_api_dict(post_dict)
    return filters.filter_post_record(post) if filters else post.to_dict()


def clean_comment(raw_node: dict, post_id: str, filters: Optional[Filters] = None) -> dict:
    """Validates raw comment dictionary through Comment class and returns standardized dict."""
    comment = Comment.from_api_dict(raw_node, post_id)
    return filters.filter_comment_record(comment) if filters else comment.to_dict()


def unpack_comment_tree(nodes: list, post_id: str, filters: Optional[Filters] = None) -> List[dict]:
    """Recursively traverses comment trees, validating nodes against Filters and applying column restrictions."""
    if filters is None:
        filters = Filters()

    flat = []
    if not isinstance(nodes, list):
        nodes = [nodes] if isinstance(nodes, dict) else []

    for node in nodes:
        if not isinstance(node, dict):
            continue

        comment = Comment.from_api_dict(node, post_id)
        if filters.is_valid_comment(comment):
            flat.append(filters.filter_comment_record(comment))

        # Recursively unpack nested replies
        replies = node.get("replies") or node.get("children") or []
        if isinstance(replies, list) and replies:
            flat.extend(unpack_comment_tree(replies, post_id, filters))

    return flat
