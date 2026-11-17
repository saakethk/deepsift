"""
Enumerations of all known Arctic Shift / Reddit API fields for Posts and Comments.
"""
import difflib
from enum import Enum
from typing import Iterable, Set, Optional, Union


class FieldEnum(str, Enum):
    """Base enumeration providing string interop, descriptions, validation, and typo hints."""
    description: str

    def __new__(cls, value: str, description: str = ""):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.description = description
        obj.__doc__ = description
        return obj

    def __str__(self) -> str:
        return self.value

    @classmethod
    def get_description(cls, value: Union[str, "FieldEnum"]) -> str:
        """Returns the description for a field, or empty string if not found."""
        val = value.value if isinstance(value, cls) else str(value).lower().strip()
        member = cls._value2member_map_.get(val)
        return member.description if member else ""

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
    def validate_many(cls, fields: Optional[Union[str, "FieldEnum", Iterable[Union[str, "FieldEnum"]]]]) -> Optional[Set[str]]:
        """
        Validates one or more fields. Returns a validated Set[str] or None if fields is None.
        """
        if fields is None:
            return None
        if isinstance(fields, (str, cls)):
            fields = [fields]
        validated = set()
        for f in fields:
            validated.add(cls.validate(f))
        return validated

    @classmethod
    def all_fields(cls) -> Set[str]:
        """Returns a set of all canonical field strings in this enumeration."""
        return {m.value for m in cls}


class PostField(FieldEnum):
    """All known Reddit / Arctic Shift post API fields with descriptions."""
    ALL_AWARDINGS = ("all_awardings", "List of Reddit awards received by this post, including coin values and icons.")
    ALLOW_LIVE_COMMENTS = ("allow_live_comments", "Whether live comment mode is enabled for the submission.")
    ARCHIVED = ("archived", "Whether the post is archived and no longer accepts votes or comments.")
    AUTHOR = ("author", "Reddit username of the post submitter.")
    AUTHOR_FLAIR_BACKGROUND_COLOR = ("author_flair_background_color", "Background hex color code for the author user flair.")
    AUTHOR_FLAIR_CSS_CLASS = ("author_flair_css_class", "CSS class name applied to author flair in old Reddit styling.")
    AUTHOR_FLAIR_RICHTEXT = ("author_flair_richtext", "Structured rich text components and emojis for author flair.")
    AUTHOR_FLAIR_TEMPLATE_ID = ("author_flair_template_id", "UUID template ID of author flair preset used.")
    AUTHOR_FLAIR_TEXT = ("author_flair_text", "Plaintext content of the author user flair.")
    AUTHOR_FLAIR_TEXT_COLOR = ("author_flair_text_color", "Text color scheme ('dark' or 'light') for author flair.")
    AUTHOR_FLAIR_TYPE = ("author_flair_type", "Type of author flair, usually 'text' or 'richtext'.")
    AUTHOR_FULLNAME = ("author_fullname", "Full Reddit account ID with 't2_' prefix of the author.")
    AUTHOR_IS_BLOCKED = ("author_is_blocked", "Whether the author is blocked by the viewing account context.")
    AUTHOR_PATREON_FLAIR = ("author_patreon_flair", "Whether the author has Patreon flair integration active.")
    AUTHOR_PREMIUM = ("author_premium", "Whether the author holds an active Reddit Premium subscription.")
    AWARDERS = ("awarders", "List of users who awarded this post.")
    BANNED_BY = ("banned_by", "Moderator or system actor that removed this post.")
    CAN_GILD = ("can_gild", "Whether the submission can receive Reddit awards.")
    CAN_MOD_POST = ("can_mod_post", "Whether viewing user has moderator permissions on this post.")
    CATEGORY = ("category", "Categorical tag of the post.")
    CLICKED = ("clicked", "Whether the post link was clicked by the authenticated session.")
    CONTENT_CATEGORIES = ("content_categories", "List of content categories assigned to the subreddit or post.")
    CONTEST_MODE = ("contest_mode", "Whether comment scores are randomized and hidden in contest mode.")
    CREATED_UTC = ("created_utc", "Unix timestamp (UTC seconds) when the post was created.")
    DISCUSSION_TYPE = ("discussion_type", "Type of discussion (e.g. 'CHAT' for live chat posts).")
    DISTINGUISHED = ("distinguished", "Distinguished status ('moderator', 'admin', or null).")
    DOMAIN = ("domain", "Domain of the submitted URL (e.g. 'self.resumes', 'i.redd.it').")
    DOWNS = ("downs", "Legacy downvote count (always 0 in modern Reddit API).")
    EDITED = ("edited", "False if unedited, or Unix timestamp UTC seconds when last edited.")
    FLAIR = ("flair", "General flair metadata object or alias if present.")
    GILDED = ("gilded", "Number of times the post received Reddit Gold.")
    GILDINGS = ("gildings", "Dictionary mapping award types to counts received.")
    HIDDEN = ("hidden", "Whether the post has been marked hidden by the user.")
    HIDE_SCORE = ("hide_score", "Whether the post score is currently hidden to users.")
    ID = ("id", "Base36 unique alphanumeric ID of the post (e.g. '1c6z2px').")
    IS_BLANK = ("is_blank", "Flag indicating if post body is empty.")
    IS_CREATED_FROM_ADS_UI = ("is_created_from_ads_ui", "Whether post was submitted through Reddit advertising UI.")
    IS_CROSSPOSTABLE = ("is_crosspostable", "Whether this post can be crossposted to other subreddits.")
    IS_GALLERY = ("is_gallery", "Whether the post contains multiple images in Reddit gallery format.")
    IS_META = ("is_meta", "Whether the submission was flagged as subreddit meta discussion.")
    IS_ORIGINAL_CONTENT = ("is_original_content", "Whether the submitter flagged the submission as Original Content.")
    IS_REDDIT_MEDIA_DOMAIN = ("is_reddit_media_domain", "Whether media is hosted on Reddit infrastructure.")
    IS_ROBOT_INDEXABLE = ("is_robot_indexable", "Whether web crawler search bots are allowed to index this post.")
    IS_SELF = ("is_self", "True if text submission (self-post), False if link or media.")
    IS_VIDEO = ("is_video", "True if this post is a native Reddit video.")
    LIKES = ("likes", "Voting state of viewing user (True for upvote, False for downvote).")
    LINK_FLAIR_BACKGROUND_COLOR = ("link_flair_background_color", "Background hex color code for the link flair.")
    LINK_FLAIR_CSS_CLASS = ("link_flair_css_class", "CSS class name applied to post flair in old Reddit styling.")
    LINK_FLAIR_RICHTEXT = ("link_flair_richtext", "Structured rich text components and emojis for link flair.")
    LINK_FLAIR_TEMPLATE_ID = ("link_flair_template_id", "UUID template ID of link flair preset used.")
    LINK_FLAIR_TEXT = ("link_flair_text", "Plaintext label of the post link flair (e.g. 'Resume Review').")
    LINK_FLAIR_TEXT_COLOR = ("link_flair_text_color", "Text color scheme ('dark' or 'light') for link flair.")
    LINK_FLAIR_TYPE = ("link_flair_type", "Type of post flair, typically 'text' or 'richtext'.")
    LOCKED = ("locked", "Whether comments are locked and disabled on this post.")
    MEDIA = ("media", "Embedded media metadata object (player dimensions, provider specs).")
    MEDIA_EMBED = ("media_embed", "Raw HTML embed code dictionary for external media.")
    MEDIA_METADATA = ("media_metadata", "Dictionary of image/media assets for galleries and inline images.")
    MEDIA_ONLY = ("media_only", "Subreddit setting flag indicating whether media-only is enforced.")
    NAME = ("name", "Full Reddit thing identifier with 't3_' prefix (e.g. 't3_1c6z2px').")
    NO_FOLLOW = ("no_follow", "Whether links in this post have HTML rel='nofollow' attached.")
    NUM_COMMENTS = ("num_comments", "Total count of comments (top-level and nested) on this post.")
    NUM_CROSSPOSTS = ("num_crossposts", "Number of times this post was crossposted to other subreddits.")
    NUM_DUPLICATES = ("num_duplicates", "Number of duplicate link submissions detected on Reddit.")
    OVER_18 = ("over_18", "Whether the post is flagged as Not Safe For Work (NSFW / 18+).")
    PARENT_WHITELIST_STATUS = ("parent_whitelist_status", "Subreddit advertising whitelist status inherited from parent.")
    PERMALINK = ("permalink", "Relative URL path to the submission on reddit.com.")
    PINNED = ("pinned", "Whether the submission is pinned to submitter user profile.")
    POST_HINT = ("post_hint", "Hint about content type ('image', 'link', 'hosted:video', 'rich:video').")
    PREVIEW = ("preview", "Thumbnail preview resolutions and image variants generated by Reddit.")
    PWLS = ("pwls", "Parent whitelist status integer code for advertising tier.")
    QUARANTINE = ("quarantine", "Whether the subreddit containing this post is quarantined.")
    REMOVAL_REASON = ("removal_reason", "Internal removal note or reason identifier if removed by moderators.")
    REMOVED_BY = ("removed_by", "Actor who removed the post (e.g. 'moderator', 'automod_filtered').")
    REMOVED_BY_CATEGORY = ("removed_by_category", "Category explaining removal ('moderator', 'deleted', 'automod_filtered').")
    RETRIEVED_ON = ("retrieved_on", "Unix timestamp when Arctic Shift/Pushshift archived this record.")
    SAVED = ("saved", "Whether the post is saved to the viewer Reddit account bookmarks.")
    SCORE = ("score", "Net score of the post (upvotes minus downvotes).")
    SECURE_MEDIA = ("secure_media", "HTTPS-secure media metadata object.")
    SECURE_MEDIA_EMBED = ("secure_media_embed", "HTTPS-secure HTML embed dictionary.")
    SELFTEXT = ("selftext", "Body text in Markdown format for text submissions.")
    SELFTEXT_HTML = ("selftext_html", "HTML-rendered version of the post Markdown selftext body.")
    SEND_REPLIES = ("send_replies", "Whether author opted to receive inbox notifications for replies.")
    SPOILER = ("spoiler", "Whether the post has been marked with a spoiler tag.")
    STICKIED = ("stickied", "Whether the post is stickied / pinned to the top of the subreddit.")
    SUBREDDIT = ("subreddit", "Name of the subreddit without prefix (e.g. 'resumes').")
    SUBREDDIT_ID = ("subreddit_id", "Full subreddit ID with 't5_' prefix (e.g. 't5_2qr79').")
    SUBREDDIT_NAME_PREFIXED = ("subreddit_name_prefixed", "Subreddit name prefixed with 'r/' (e.g. 'r/resumes').")
    SUBREDDIT_SUBSCRIBERS = ("subreddit_subscribers", "Subscriber count of the subreddit at archiving time.")
    SUBREDDIT_TYPE = ("subreddit_type", "Visibility status of subreddit ('public', 'restricted', 'private').")
    SUGGESTED_SORT = ("suggested_sort", "Recommended comment sorting order ('confidence', 'top', 'new', 'qa').")
    THUMBNAIL = ("thumbnail", "URL of thumbnail image or placeholder ('self', 'default', 'nsfw').")
    THUMBNAIL_HEIGHT = ("thumbnail_height", "Height of thumbnail image in pixels.")
    THUMBNAIL_WIDTH = ("thumbnail_width", "Width of thumbnail image in pixels.")
    TITLE = ("title", "Submission title text.")
    TOP_AWARDED_TYPE = ("top_awarded_type", "Type or tier of top award if heavily awarded.")
    TOTAL_AWARDS_RECEIVED = ("total_awards_received", "Aggregate count of all awards received on this post.")
    TREATMENT_TAGS = ("treatment_tags", "Special UI treatment tags applied by Reddit.")
    UPS = ("ups", "Upvotes count (matches score in modern Reddit API).")
    UPVOTE_RATIO = ("upvote_ratio", "Ratio of upvotes to total votes (e.g. 0.95 for 95% upvoted).")
    URL = ("url", "Target URL (external link, media file, or permalink if self-post).")
    URL_OVERRIDDEN_BY_DEST = ("url_overridden_by_dest", "Original destination link before Reddit URL overrides.")
    VIEW_COUNT = ("view_count", "Total post view count (typically null for public API).")
    VISITED = ("visited", "Whether the post has been visited by the viewing user session.")
    WHITELIST_STATUS = ("whitelist_status", "Subreddit advertising whitelist tier status string.")
    WLS = ("wls", "Subreddit advertising whitelist tier integer code.")


class CommentField(FieldEnum):
    """All known Reddit / Arctic Shift comment API fields with descriptions."""
    ALL_AWARDINGS = ("all_awardings", "List of Reddit awards received by this comment.")
    ARCHIVED = ("archived", "Whether the comment is archived and cannot receive new votes or replies.")
    ASSOCIATED_AWARD = ("associated_award", "Details of award that generated this comment if applicable.")
    AUTHOR = ("author", "Reddit username of the comment author.")
    AUTHOR_FLAIR_BACKGROUND_COLOR = ("author_flair_background_color", "Background hex color code for author user flair.")
    AUTHOR_FLAIR_CSS_CLASS = ("author_flair_css_class", "CSS class name applied to author flair in old Reddit styling.")
    AUTHOR_FLAIR_RICHTEXT = ("author_flair_richtext", "Structured rich text components and emojis for author flair.")
    AUTHOR_FLAIR_TEMPLATE_ID = ("author_flair_template_id", "UUID template ID of author flair preset used.")
    AUTHOR_FLAIR_TEXT = ("author_flair_text", "Plaintext content of the author user flair.")
    AUTHOR_FLAIR_TEXT_COLOR = ("author_flair_text_color", "Text color scheme ('dark' or 'light') for author flair.")
    AUTHOR_FLAIR_TYPE = ("author_flair_type", "Type of author flair, usually 'text' or 'richtext'.")
    AUTHOR_FULLNAME = ("author_fullname", "Full Reddit account ID with 't2_' prefix of the author.")
    AUTHOR_IS_BLOCKED = ("author_is_blocked", "Whether the author is blocked by viewing account context.")
    AUTHOR_PATREON_FLAIR = ("author_patreon_flair", "Whether the author has Patreon flair integration active.")
    AUTHOR_PREMIUM = ("author_premium", "Whether the author holds an active Reddit Premium subscription.")
    AWARDERS = ("awarders", "List of users who awarded this comment.")
    BANNED_BY = ("banned_by", "Moderator or system actor that removed this comment.")
    BODY = ("body", "Body text of the comment in Markdown format.")
    BODY_HTML = ("body_html", "HTML-rendered version of the comment Markdown body.")
    CAN_GILD = ("can_gild", "Whether the comment can receive Reddit awards.")
    CAN_MOD_POST = ("can_mod_post", "Whether viewing user has moderator permissions on this comment.")
    COLLAPSED = ("collapsed", "Whether comment is collapsed by default in Reddit UI.")
    COLLAPSED_BECAUSE_CROWD_CONTROL = ("collapsed_because_crowd_control", "Whether comment was auto-collapsed by Reddit Crowd Control.")
    COLLAPSED_REASON = ("collapsed_reason", "Explanation why comment was collapsed (e.g. 'low score').")
    COMMENT_ID = ("comment_id", "Normalized base36 comment ID without prefix (alias of id).")
    COMMENT_TYPE = ("comment_type", "Type tag for special comments (e.g. moderator note, prediction).")
    CONTROVERSIALITY = ("controversiality", "Controversiality metric (1 if balanced upvotes/downvotes, 0 otherwise).")
    CREATED_UTC = ("created_utc", "Unix timestamp (UTC seconds) when the comment was posted.")
    DISTINGUISHED = ("distinguished", "Distinguished status ('moderator', 'admin', or null).")
    DOWNS = ("downs", "Legacy downvote count (always 0 in modern Reddit API).")
    EDITED = ("edited", "False if unedited, or Unix timestamp UTC seconds when last edited.")
    GILDED = ("gilded", "Number of times the comment received Reddit Gold.")
    GILDINGS = ("gildings", "Dictionary mapping award types to counts received.")
    ID = ("id", "Base36 unique alphanumeric ID of the comment (e.g. 'c6z2pxa').")
    IS_SUBMITTER = ("is_submitter", "True if comment author is original submitter (OP) of the post.")
    LIKES = ("likes", "Voting state of viewing user (True for upvote, False for downvote).")
    LINK_ID = ("link_id", "Full ID with 't3_' prefix of parent post this comment belongs to.")
    LOCKED = ("locked", "Whether replies to this comment are locked and disabled.")
    NAME = ("name", "Full Reddit thing identifier with 't1_' prefix (e.g. 't1_c6z2pxa').")
    NO_FOLLOW = ("no_follow", "Whether links in this comment have HTML rel='nofollow' attached.")
    PARENT_ID = ("parent_id", "Immediate parent ID ('t3_' for submission/top-level, 't1_' for comment).")
    PERMALINK = ("permalink", "Relative URL path to the comment on reddit.com.")
    POST_ID = ("post_id", "Base36 ID of the parent post without 't3_' prefix.")
    QUARANTINE = ("quarantine", "Whether the subreddit containing this comment is quarantined.")
    REMOVAL_REASON = ("removal_reason", "Internal removal note or reason identifier if removed by moderators.")
    RETRIEVED_ON = ("retrieved_on", "Unix timestamp when Arctic Shift/Pushshift archived this record.")
    SAVED = ("saved", "Whether comment is saved to viewer Reddit account bookmarks.")
    SCORE = ("score", "Net score of the comment (upvotes minus downvotes).")
    SCORE_HIDDEN = ("score_hidden", "Whether comment score is temporarily hidden by subreddit rule.")
    SEND_REPLIES = ("send_replies", "Whether author opted to receive inbox notifications for replies.")
    STICKIED = ("stickied", "Whether comment is stickied / pinned to top of comment section.")
    SUBREDDIT = ("subreddit", "Name of the subreddit without prefix (e.g. 'resumes').")
    SUBREDDIT_ID = ("subreddit_id", "Full subreddit ID with 't5_' prefix (e.g. 't5_2qr79').")
    SUBREDDIT_NAME_PREFIXED = ("subreddit_name_prefixed", "Subreddit name prefixed with 'r/' (e.g. 'r/resumes').")
    SUBREDDIT_TYPE = ("subreddit_type", "Visibility status of subreddit ('public', 'restricted', 'private').")
    TOP_AWARDED_TYPE = ("top_awarded_type", "Type or tier of top award if heavily awarded.")
    TOTAL_AWARDS_RECEIVED = ("total_awards_received", "Aggregate count of all awards received on this comment.")
    TREATMENT_TAGS = ("treatment_tags", "Special UI treatment tags applied by Reddit.")
    UNREPLIABLE_REASON = ("unrepliable_reason", "Reason why replies cannot be posted (e.g. blocked user, locked thread).")
    UPS = ("ups", "Upvotes count (matches score in modern Reddit API).")
