"""
Cohort filtering logic for Reddit resume research.
Criteria:
1. Score > 0
2. Num comments > 10
3. URL points to an image file (.png, .jpeg, .jpg)
"""

def is_picture_url(url: str) -> bool:
    """Checks if a URL points to an image (.png or .jpeg / .jpg)."""
    clean = (url or "").lower().split("?")[0].strip()
    return clean.endswith((".png", ".jpg", ".jpeg")) or ("i.redd.it" in clean)


def is_cohort_candidate(post: dict) -> bool:
    """Validates if a post has score > 0, num_comments > 10, and a picture URL."""
    return (
        (post.get("score") or 0) > 0
        and (post.get("num_comments") or 0) > 10
        and is_picture_url(post.get("url"))
    )
