"""
Enumerations of all known Arctic Shift / Reddit API fields for Posts and Comments.
"""
import difflib
from enum import Enum
from typing import Iterable, Set, Optional, Union


class FieldEnum(str, Enum):
    """Base enumeration providing string interop, validation, and typo hints."""

    def __str__(self) -> str:
        return self.value

    @classmethod
    def has_field(cls, value: Union[str, "FieldEnum"]) -> bool:
        """Checks if a field exists in this enumeration."""
        val = value.value if isinstance(value, cls) else str(value).lower().strip()
        return val in cls._value2member_map_

    @classmethod
    def validate(cls, value: Union[str, "FieldEnum"]) -> str:
        """
        Validates that a field is in this enumeration.
        Returns canonical field string or raises ValueError with typo suggestions.
        """
        val = value.value if isinstance(value, cls) else str(value).strip()
        if val in cls._value2member_map_:
            return val
        val_lower = val.lower()
        if val_lower in cls._value2member_map_:
            return val_lower

        matches = difflib.get_close_matches(val_lower, [m.value for m in cls], n=1, cutoff=0.55)
        hint = f" Did you mean '{matches[0]}'?" if matches else ""
        raise ValueError(f"Invalid {cls.__name__} field '{val}'.{hint}")

    @classmethod
    def validate_many(cls, fields: Optional[Iterable[Union[str, "FieldEnum"]]]) -> Optional[Set[str]]:
        """
        Validates an iterable of fields. Returns a validated Set[str] or None if fields is None.
        """
        if fields is None:
            return None
        validated = set()
        for f in fields:
            validated.add(cls.validate(f))
        return validated

    @classmethod
    def all_fields(cls) -> Set[str]:
        """Returns a set of all canonical field strings in this enumeration."""
        return {m.value for m in cls}


class PostField(FieldEnum):
    """All known Reddit / Arctic Shift post API fields."""
    ALL_AWARDINGS = "all_awardings"
    ALLOW_LIVE_COMMENTS = "allow_live_comments"
    ARCHIVED = "archived"
    AUTHOR = "author"
    AUTHOR_FLAIR_BACKGROUND_COLOR = "author_flair_background_color"
    AUTHOR_FLAIR_CSS_CLASS = "author_flair_css_class"
    AUTHOR_FLAIR_RICHTEXT = "author_flair_richtext"
    AUTHOR_FLAIR_TEMPLATE_ID = "author_flair_template_id"
    AUTHOR_FLAIR_TEXT = "author_flair_text"
    AUTHOR_FLAIR_TEXT_COLOR = "author_flair_text_color"
    AUTHOR_FLAIR_TYPE = "author_flair_type"
    AUTHOR_FULLNAME = "author_fullname"
    AUTHOR_IS_BLOCKED = "author_is_blocked"
    AUTHOR_PATREON_FLAIR = "author_patreon_flair"
    AUTHOR_PREMIUM = "author_premium"
    AWARDERS = "awarders"
    BANNED_BY = "banned_by"
    CAN_GILD = "can_gild"
    CAN_MOD_POST = "can_mod_post"
    CATEGORY = "category"
    CLICKED = "clicked"
    CONTENT_CATEGORIES = "content_categories"
    CONTEST_MODE = "contest_mode"
    CREATED_UTC = "created_utc"
    DISCUSSION_TYPE = "discussion_type"
    DISTINGUISHED = "distinguished"
    DOMAIN = "domain"
    DOWNS = "downs"
    EDITED = "edited"
    FLAIR = "flair"
    GILDED = "gilded"
    GILDINGS = "gildings"
    HIDDEN = "hidden"
    HIDE_SCORE = "hide_score"
    ID = "id"
    IS_BLANK = "is_blank"
    IS_CREATED_FROM_ADS_UI = "is_created_from_ads_ui"
    IS_CROSSPOSTABLE = "is_crosspostable"
    IS_GALLERY = "is_gallery"
    IS_META = "is_meta"
    IS_ORIGINAL_CONTENT = "is_original_content"
    IS_REDDIT_MEDIA_DOMAIN = "is_reddit_media_domain"
    IS_ROBOT_INDEXABLE = "is_robot_indexable"
    IS_SELF = "is_self"
    IS_VIDEO = "is_video"
    LIKES = "likes"
    LINK_FLAIR_BACKGROUND_COLOR = "link_flair_background_color"
    LINK_FLAIR_CSS_CLASS = "link_flair_css_class"
    LINK_FLAIR_RICHTEXT = "link_flair_richtext"
    LINK_FLAIR_TEMPLATE_ID = "link_flair_template_id"
    LINK_FLAIR_TEXT = "link_flair_text"
    LINK_FLAIR_TEXT_COLOR = "link_flair_text_color"
    LINK_FLAIR_TYPE = "link_flair_type"
    LOCKED = "locked"
    MEDIA = "media"
    MEDIA_EMBED = "media_embed"
    MEDIA_METADATA = "media_metadata"
    MEDIA_ONLY = "media_only"
    NAME = "name"
    NO_FOLLOW = "no_follow"
    NUM_COMMENTS = "num_comments"
    NUM_CROSSPOSTS = "num_crossposts"
    NUM_DUPLICATES = "num_duplicates"
    OVER_18 = "over_18"
    PARENT_WHITELIST_STATUS = "parent_whitelist_status"
    PERMALINK = "permalink"
    PINNED = "pinned"
    POST_HINT = "post_hint"
    PREVIEW = "preview"
    PWLS = "pwls"
    QUARANTINE = "quarantine"
    REMOVAL_REASON = "removal_reason"
    REMOVED_BY = "removed_by"
    REMOVED_BY_CATEGORY = "removed_by_category"
    RETRIEVED_ON = "retrieved_on"
    SAVED = "saved"
    SCORE = "score"
    SECURE_MEDIA = "secure_media"
    SECURE_MEDIA_EMBED = "secure_media_embed"
    SELFTEXT = "selftext"
    SELFTEXT_HTML = "selftext_html"
    SEND_REPLIES = "send_replies"
    SPOILER = "spoiler"
    STICKIED = "stickied"
    SUBREDDIT = "subreddit"
    SUBREDDIT_ID = "subreddit_id"
    SUBREDDIT_NAME_PREFIXED = "subreddit_name_prefixed"
    SUBREDDIT_SUBSCRIBERS = "subreddit_subscribers"
    SUBREDDIT_TYPE = "subreddit_type"
    SUGGESTED_SORT = "suggested_sort"
    THUMBNAIL = "thumbnail"
    THUMBNAIL_HEIGHT = "thumbnail_height"
    THUMBNAIL_WIDTH = "thumbnail_width"
    TITLE = "title"
    TOP_AWARDED_TYPE = "top_awarded_type"
    TOTAL_AWARDS_RECEIVED = "total_awards_received"
    TREATMENT_TAGS = "treatment_tags"
    UPS = "ups"
    UPVOTE_RATIO = "upvote_ratio"
    URL = "url"
    URL_OVERRIDDEN_BY_DEST = "url_overridden_by_dest"
    VIEW_COUNT = "view_count"
    VISITED = "visited"
    WHITELIST_STATUS = "whitelist_status"
    WLS = "wls"


class CommentField(FieldEnum):
    """All known Reddit / Arctic Shift comment API fields."""
    ALL_AWARDINGS = "all_awardings"
    ARCHIVED = "archived"
    ASSOCIATED_AWARD = "associated_award"
    AUTHOR = "author"
    AUTHOR_FLAIR_BACKGROUND_COLOR = "author_flair_background_color"
    AUTHOR_FLAIR_CSS_CLASS = "author_flair_css_class"
    AUTHOR_FLAIR_RICHTEXT = "author_flair_richtext"
    AUTHOR_FLAIR_TEMPLATE_ID = "author_flair_template_id"
    AUTHOR_FLAIR_TEXT = "author_flair_text"
    AUTHOR_FLAIR_TEXT_COLOR = "author_flair_text_color"
    AUTHOR_FLAIR_TYPE = "author_flair_type"
    AUTHOR_FULLNAME = "author_fullname"
    AUTHOR_IS_BLOCKED = "author_is_blocked"
    AUTHOR_PATREON_FLAIR = "author_patreon_flair"
    AUTHOR_PREMIUM = "author_premium"
    AWARDERS = "awarders"
    BANNED_BY = "banned_by"
    BODY = "body"
    BODY_HTML = "body_html"
    CAN_GILD = "can_gild"
    CAN_MOD_POST = "can_mod_post"
    COLLAPSED = "collapsed"
    COLLAPSED_BECAUSE_CROWD_CONTROL = "collapsed_because_crowd_control"
    COLLAPSED_REASON = "collapsed_reason"
    COMMENT_ID = "comment_id"
    COMMENT_TYPE = "comment_type"
    CONTROVERSIALITY = "controversiality"
    CREATED_UTC = "created_utc"
    DISTINGUISHED = "distinguished"
    DOWNS = "downs"
    EDITED = "edited"
    GILDED = "gilded"
    GILDINGS = "gildings"
    ID = "id"
    IS_SUBMITTER = "is_submitter"
    LIKES = "likes"
    LINK_ID = "link_id"
    LOCKED = "locked"
    NAME = "name"
    NO_FOLLOW = "no_follow"
    PARENT_ID = "parent_id"
    PERMALINK = "permalink"
    POST_ID = "post_id"
    QUARANTINE = "quarantine"
    REMOVAL_REASON = "removal_reason"
    RETRIEVED_ON = "retrieved_on"
    SAVED = "saved"
    SCORE = "score"
    SCORE_HIDDEN = "score_hidden"
    SEND_REPLIES = "send_replies"
    STICKIED = "stickied"
    SUBREDDIT = "subreddit"
    SUBREDDIT_ID = "subreddit_id"
    SUBREDDIT_NAME_PREFIXED = "subreddit_name_prefixed"
    SUBREDDIT_TYPE = "subreddit_type"
    TOP_AWARDED_TYPE = "top_awarded_type"
    TOTAL_AWARDS_RECEIVED = "total_awards_received"
    TREATMENT_TAGS = "treatment_tags"
    UNREPLIABLE_REASON = "unrepliable_reason"
    UPS = "ups"
