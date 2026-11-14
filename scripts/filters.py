"""
Business rules and cohort filtering criteria for Reddit resume research.
"""

def is_picture_url(url: str) -> bool:
    """Checks if a URL corresponds to an image (.png or .jpeg / .jpg)."""
    clean = (url or "").lower().split("?")[0].strip()
    return clean.endswith((".png", ".jpg", ".jpeg")) or ("i.redd.it" in clean)


def is_cohort_post(post: dict) -> bool:
    """
    Cohort post criteria:
    - score > 0
    - num_comments > 10
    - associated URL points to an image
    """
    return (
        (post.get("score") or 0) > 0
        and (post.get("num_comments") or 0) > 10
        and is_picture_url(post.get("url"))
    )


def is_valid_comment(comment_data: dict) -> bool:
    """
    Comment filter criteria:
    - Excludes AutoModerator
    - Excludes empty, blank text bodies, and single-word comments
    """
    author = str(comment_data.get("author") or "").strip().lower()
    body = str(comment_data.get("body") or "").strip()

    if author == "automoderator":
        return False
    if not body or len(body.split()) <= 1:
        return False

    return True
