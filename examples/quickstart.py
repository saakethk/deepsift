import os
import pandas as pd
from deepsift import (
    CommentField,
    Filters,
    PostField,
    RedditScraper,
    ArcticShiftSource,
)

# 1. Define selective field projection and predicates
# Server-side projection requests only the exact attributes your analysis needs,
# cutting down wire bandwidth by up to 24x.
filters = Filters(
    post_include_fields=[
        PostField.ID,
        PostField.TITLE,
        PostField.SELFTEXT,
        PostField.SCORE,
        PostField.NUM_COMMENTS,
        PostField.AUTHOR,
        PostField.CREATED_UTC,
        PostField.SUBREDDIT,
    ],
    comment_include_fields=[
        CommentField.ID,
        CommentField.POST_ID,
        CommentField.PARENT_ID,
        CommentField.AUTHOR,
        CommentField.BODY,
        CommentField.SCORE,
        CommentField.CREATED_UTC,
    ],
    post_filter=lambda p: (p.score or 0) >= 1,
    comment_filter=lambda c: len(c.body or "") >= 10,
)

# 2. Configure ArcticShiftSource with connection parameters
source = ArcticShiftSource(timeout=30.0)

# Configure parallel workers and temporal shard granularity
scraper = RedditScraper(
    filters=filters,
    source=source,
    post_workers=2,
    comment_workers=3,
    shard_days=1,
)

# 3. Run the ingestion pipeline (using a 2-day historical window)
print("Starting DeepSift ingestion pipeline...")
posts_path = "data/ml_posts.parquet"
comments_path = "data/ml_comments.parquet"

post_ids, comment_count = scraper.run(
    subreddits=["MachineLearning"],
    from_dt="2024-01-01",
    to_dt="2024-01-03",
    posts_output=posts_path,
    comments_output=comments_path,
    errors_output="data/errors.json",
)

print(f"\nPipeline Complete:")
print(f" - Scraped {len(post_ids)} curated posts")
print(f" - Scraped {comment_count} comments")

# 4. Safely inspect the generated Parquet files
if post_ids and os.path.exists(posts_path):
    df_posts = pd.read_parquet(posts_path)
    print("\n--- Posts Sample ---")
    print(df_posts[["title", "score", "num_comments"]].head())
else:
    print("\nNo posts were retrieved. Check 'data/errors.json' for network details.")

if comment_count > 0 and os.path.exists(comments_path):
    df_comments = pd.read_parquet(comments_path)
    print("\n--- Comments Sample ---")
    print(df_comments[["author", "score", "body"]].head())
