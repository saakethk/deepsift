"""
Data transformation functions that convert raw Arctic Shift JSON into standardized dictionaries.
"""
from scripts.filters import is_valid_comment


def clean_post(post: dict) -> dict:
    """Extracts and normalizes post fields into standard schema."""
    return {
        "id": str(post.get("id")),
        "subreddit": str(post.get("subreddit") or "resumes"),
        "title": str(post.get("title") or ""),
        "selftext": str(post.get("selftext") or ""),
        "url": str(post.get("url") or ""),
        "score": int(post.get("score") or 0),
        "num_comments": int(post.get("num_comments") or 0),
        "flair": str(post.get("link_flair_text") or ""),
        "created_utc": int(post.get("created_utc") or 0),
    }


def clean_comment(raw_node: dict, post_id: str) -> dict:
    """Unwraps and normalizes raw comment node into standard schema."""
    data = raw_node.get("comment") or raw_node.get("data") or raw_node
    return {
        "comment_id": str(data.get("id") or data.get("comment_id") or data.get("name") or "None"),
        "post_id": str(post_id),
        "author": str(data.get("author") or "[deleted]"),
        "body": str(data.get("body") or ""),
        "score": int(data.get("score") or 0),
        "created_utc": int(data.get("created_utc") or 0),
        "parent_id": str(data.get("parent_id") or ""),
    }


def unpack_comment_tree(nodes: list, post_id: str) -> list[dict]:
    """Recursively flattens nested comment tree nodes and applies validation filters."""
    flat = []
    if not isinstance(nodes, list):
        nodes = [nodes] if isinstance(nodes, dict) else []

    for node in nodes:
        if not isinstance(node, dict):
            continue

        comment = clean_comment(node, post_id)
        if is_valid_comment(comment):
            flat.append(comment)

        # Recursively unpack nested child replies
        replies = node.get("replies") or node.get("children") or []
        if isinstance(replies, list) and replies:
            flat.extend(unpack_comment_tree(replies, post_id))

    return flat
