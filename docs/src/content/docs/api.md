---
title: Python API Reference
description: Technical class, method, and exception reference for DeepSift modules.
---

Detailed technical reference for the core DeepSift library modules.

---

## `RedditScraper`

Defined in `deepsift.scraper.RedditScraper`. Orchestrates multi-worker post and comment extraction.

### Constructor

```python
RedditScraper(
    filters: Optional[Filters] = None,
    source: Optional[Source] = None,
    storage_cls: Type[Storage] = ParquetStorage,
    post_workers: int = 4,
    comment_workers: int = 5,
    shard_days: int = 180,
)
```

- **`filters`**: A `Filters` instance specifying inclusion/exclusion fields and predicate callables. Defaults to accepting all items.
- **`source`**: Data source provider instance. Defaults to `ArcticShiftSource()`.
- **`storage_cls`**: Storage streaming writer class. Defaults to `ParquetStorage`.
- **`post_workers`**: Number of concurrent thread workers for post shards. Must be `>= 1`.
- **`comment_workers`**: Concurrency limit for async comment tree scraping. Must be `>= 1`.
- **`shard_days`**: Time window size in days per worker shard. Must be `>= 1`.

### Core Methods

- **`scrape_posts(...) -> List[str]`**: Scrapes posts matching filters and writes to Parquet.
- **`scrape_comments(...) -> int`**: Asynchronously extracts comments for a collection of post IDs.
- **`run(...) -> Tuple[List[str], int]`**: Executes post scraping followed by comment extraction.
- **`save_errors_log(errors_path="data/errors.json", fatal_error=None) -> Optional[str]`**: Writes structured JSON error log.

---

## `Filters`

Defined in `deepsift.filters.Filters`. Manages record predicates and server-side projection math.

### Constructor

```python
Filters(
    post_filter: Optional[Callable[[Post], bool]] = None,
    comment_filter: Optional[Callable[[Comment], bool]] = None,
    post_include_fields: Optional[Iterable[Union[str, PostField]]] = None,
    comment_include_fields: Optional[Iterable[Union[str, CommentField]]] = None,
    post_exclude_fields: Optional[Iterable[Union[str, PostField]]] = None,
    comment_exclude_fields: Optional[Iterable[Union[str, CommentField]]] = None,
    additional_filter_fields: Optional[Iterable[Union[str, PostField]]] = None,
    validate: bool = True,
)
```

- Excluding required fields (`id`, `created_utc`, `subreddit` for posts; `id`, `post_id`, `parent_id` for comments) raises `RequiredFieldError`.

---

## `Post` & `Comment` Models

Defined in `deepsift.models`.

- **Prefix Normalization**: `t3_` and `t1_` prefixes are stripped from IDs.
- **`UnretrievedFieldError`**: Raised when accessing an attribute that was not included in the server-side projection.
- **Typo Suggestions**: Invalid field accesses raise `AttributeError` with fuzzy match recommendations (e.g. `post.subreddt` -> suggests `subreddit`).
- **`is_top_level`**: Property on `Comment` indicating whether it directly replies to a post (`parent_id` starts with `t3_`).

---

## `PostField` & `CommentField`

Defined in `deepsift.models.enums`.

- Enumerates 105+ known Reddit post fields and all known comment attributes with inline documentation.
- `PostField.validate(field_name)`: Validates field strings with typo suggestions.
- `PostField.get_description(field_name)`: Returns the documentation string for that field.

---

## `ParquetStorage`

Defined in `deepsift.storage.parquet.ParquetStorage`.

- Thread-safe PyArrow streaming writer.
- Sanitizes polymorphic schema attributes (such as `edited`, flairs, and distinguished values) into strings across batch boundaries.
- Flushes data directly to disk, keeping memory consumption low and constant.
