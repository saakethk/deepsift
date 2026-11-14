"""
Cohort filtering logic for Reddit resume research.
Criteria:
1. Score > 0
2. Num comments > 10
3. URL points to an image file (.png, .jpeg, .jpg)
"""

def is_picture_url(url: str) -> bool:
    """Checks if a URL corresponds to an image (.png or .jpeg / .jpg)."""
    if not isinstance(url, str):
        return False
    clean = url.lower().split("?")[0].strip()
    return clean.endswith((".png", ".jpg", ".jpeg")) or ("i.redd.it" in clean)


def is_cohort_candidate(post: dict) -> bool:
    """
    Validates if a post matches the cohort requirements:
    - score > 0
    - num_comments > 10
    - associated url is an image (.png or jpeg)
    """
    score = post.get("score") or 0
    num_comments = post.get("num_comments") or 0
    url = post.get("url") or ""

    return (score > 0) and (num_comments > 10) and is_picture_url(url)
