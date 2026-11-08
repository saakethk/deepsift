"""
clean_ipeds_dataset.py

Utilities for cleaning and structuring IPEDS college data and crawled URL paths.
"""

from __future__ import annotations

import glob
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

try:
    from helpers.url_crawler import crawl
except ImportError:
    try:
        from .url_crawler import crawl
    except ImportError:
        from url_crawler import crawl


# Regex patterns for identifying relevant career / resume subpaths vs noise
_RELEVANT_MEDIA_EXT_RE = re.compile(
    r"\.(?:jpe?g|png|gif|svg|webp|ico|mp3|mp4|wav|avi|css|js|json|xml|zip|tar|gz)(?:\?.*)?$",
    re.IGNORECASE,
)

_RELEVANT_NOISE_RE = re.compile(
    r"(?:classes|courses|instruction|operations|school|activities|competition|session|league|play|fall|spring|winter|summer)[-_ ]resumes?"
    r"|resumenes[-_ ]para"
    r"|/faculty/cv/"
    r"|/facstaff/.*cv"
    r"|/faculty/.*\.pdf"
    r"|human[-_ ]resources/careers"
    r"|/hr/careers"
    r"|careers[-_ ]at[-_ ]"
    r"|working[-_ ]at[-_ ]"
    r"|employment[-_ ]at[-_ ]"
    r"|jobs?[-_ ]at[-_ ]"
    r"|faculty[-_ ]openings"
    r"|staff[-_ ]openings"
    r"|job[-_ ]openings"
    r"|salary[-_ ]grades"
    r"|/athletics/"
    r"|/sports/"
    r"|news/.*(?:career|resume)"
    r"|inside[-_ ][a-z0-9_-]+/news/"
    r"|press[-_ ]release"
    r"|/blog/\d{4}/",
    re.IGNORECASE,
)

_RELEVANT_TARGET_RE = re.compile(
    # 1. Direct Resume / CV / Cover Letter / VMock / Big Interview
    r"(?:^|[/._ -])(?:resumes?|curriculum[-_ ]vitae|cover[-_ ]letters?|coverletters?|vmock)(?:[/._ -]|$|\.(?:pdf|html|php|aspx?|docx?))"
    # 2. Career Center & Services Hubs
    r"|career[-_ ](?:services|center|development|readiness|resources|advising|counseling|planning|hub|prep|coaching|guidance|closet|exploration|pathways|success)"
    r"|careercenter|careerservices|careerdevelopment|careerreadiness|careerhub"
    # 3. Job Search, Interview Prep, Handshake
    r"|job[-_ ]search|jobsearch|interview[-_ ]prep|mock[-_ ]interview|interviewing[-_ ]tips|dress[-_ ]to[-_ ]impress"
    r"|big[-_ ]interview|standout|handshake/(?:students|resources|jobs|events)"
    # 4. Career Fairs & Student Internship Guides
    r"|career[-_ ]fair|careerfair|internship[-_ ](?:guide|resources|program|prep|handbook|opportunities)",
    re.IGNORECASE,
)


def is_relevant_subpath(subpath: str | None) -> bool:
    """
    Determine whether a crawled subpath is relevant to career services,
    resume tips/templates, cover letters, and job search prep.
    """
    if not subpath or pd.isna(subpath):
        return False
    path = str(subpath).strip()
    if _RELEVANT_MEDIA_EXT_RE.search(path):
        return False
    if _RELEVANT_NOISE_RE.search(path):
        return False
    return bool(_RELEVANT_TARGET_RE.search(path))


def classify_relevant_subpaths(
    df: pd.DataFrame,
    subpath_col: str = "subpaths",
    target_col: str = "relevant",
    inplace: bool = False,
) -> pd.DataFrame:
    """
    Apply relevance rules to a DataFrame of subpaths, updating the target column with boolean flags.
    """
    res = df if inplace else df.copy()
    if subpath_col in res.columns:
        res[target_col] = res[subpath_col].apply(is_relevant_subpath)
    return res


def _clean_root_url(raw: str | None) -> str:
    """Normalize a raw web address into a canonical root URL (e.g. 'https://www.harvard.edu')."""
    if pd.isna(raw):
        return ""
    raw = str(raw).strip()
    # Handle IPEDS missing / invalid codes (-1, -2, -3, etc.) or email addresses
    if raw in {"-1", "-2", "-3", "", "nan", "none", "null"} or "@" in raw:
        return ""

    # Remove any duplicate or mixed-case http(s):// prefixes
    raw = re.sub(r"^(https?://)+", "", raw, flags=re.IGNORECASE)
    raw = f"https://{raw}"

    parsed = urlparse(raw)
    netloc = parsed.netloc.lower().strip()

    # Must have a valid domain structure with at least one dot and no email '@'
    if not netloc or "." not in netloc or "@" in netloc:
        return ""

    return f"https://{netloc}"


def _extract_subpath(url: str | None) -> str:
    """Extract the relative subpath and query parameters from a URL."""
    if not url or pd.isna(url):
        return "/"
    url = str(url).strip()
    if url.startswith("/"):
        return url

    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return path


def _read_ipeds_file(filepath: str | Path) -> pd.DataFrame:
    """Read an IPEDS CSV file handling UTF-8 vs Latin-1 encoding differences."""
    try:
        df = pd.read_csv(filepath, encoding="utf-8-sig", low_memory=False)
    except UnicodeDecodeError:
        df = pd.read_csv(filepath, encoding="latin1", low_memory=False)

    df.columns = df.columns.str.strip().str.lower()
    return df


def create_unique_universities_table(
    directory_path: str | Path,
) -> pd.DataFrame:
    """
    Produce a table of unique universities and their websites matching the
    notebook's deduplication logic, with start and end years.

    Args:
        directory_path: Path to the directory containing IPEDS CSV files
                        (e.g. 'data/IPEDS_hd_data').

    Returns:
        pd.DataFrame with columns:
            - 'university_name': Name of the institution
            - 'root_url': Normalized root website (e.g. 'https://www.harvard.edu')
            - 'start_year': Earliest year the university was recorded
            - 'end_year': Most recent year the university was recorded
    """
    # 1. Load data from directory path
    if isinstance(directory_path, (str, Path)):
        path = Path(directory_path)
        if not path.exists():
            raise FileNotFoundError(f"Directory or file does not exist: {directory_path}")

        if path.is_dir():
            files = sorted(glob.glob(str(path / "*.csv")))
            if not files:
                raise FileNotFoundError(f"No CSV files found in: {directory_path}")
            dfs = []
            for f in files:
                df_year = _read_ipeds_file(f)
                match = re.search(r"\d{4}", os.path.basename(f))
                year = int(match.group()) if match else None
                df_year["report_year"] = year

                name_c = next((c for c in ["instnm", "university_name", "university name", "name"] if c in df_year.columns), None)
                web_c = next((c for c in ["webaddr", "web_addr", "root_url", "root url", "website"] if c in df_year.columns), None)
                if name_c and web_c:
                    sub = df_year[[name_c, web_c, "report_year"]].rename(
                        columns={name_c: "instnm", web_c: "webaddr"}
                    )
                    dfs.append(sub)
                else:
                    dfs.append(df_year)
            df = pd.concat(dfs, ignore_index=True)
        else:
            df = _read_ipeds_file(path)
    elif isinstance(directory_path, pd.DataFrame):
        df = directory_path.copy()
    else:
        raise TypeError(
            f"Expected directory path as str or Path, got {type(directory_path).__name__}"
        )

    if df.empty:
        return pd.DataFrame(
            columns=["university_name", "root_url", "start_year", "end_year"]
        )

    df.columns = df.columns.str.strip().str.lower()
    name_col = next((c for c in ["instnm", "university_name", "university name", "name"] if c in df.columns), "instnm")
    web_col = next((c for c in ["webaddr", "web_addr", "root_url", "root url", "website"] if c in df.columns), "webaddr")
    year_col = next((c for c in ["report_year", "year", "data_year", "data year"] if c in df.columns), None)

    # 1. Calculate overall start_year and end_year per university across all records
    if year_col:
        df[year_col] = pd.to_numeric(df[year_col], errors="coerce")
        years_agg = df.groupby(name_col)[year_col].agg(
            start_year="min",
            end_year="max",
        ).reset_index()
    else:
        years_agg = pd.DataFrame({name_col: df[name_col].unique(), "start_year": None, "end_year": None})

    # 2. Replicate the notebook deduplication (dedup on webaddr, then group by instnm)
    subset_colleges = df.drop_duplicates(subset=web_col)
    all_colleges = subset_colleges.groupby(name_col)[web_col].last().reset_index()

    # 3. Merge years with unique universities
    merged = pd.merge(all_colleges, years_agg, on=name_col, how="left")

    # 4. Clean root URL and format column names
    merged["root_url"] = merged[web_col].apply(_clean_root_url)

    # 5. Filter out empty, invalid URLs, and email addresses
    merged = merged[merged["root_url"] != ""].copy()
    merged = merged.rename(columns={name_col: "university_name"})
    merged["university_name"] = merged["university_name"].astype(str).str.strip()

    # 6. Deduplicate by root_url so each website domain is only crawled once
    # Merges start and end years across branch campuses sharing the same domain
    merged = (
        merged.groupby("root_url")
        .agg(
            university_name=("university_name", "last"),
            start_year=("start_year", "min"),
            end_year=("end_year", "max"),
        )
        .reset_index()
    )

    if year_col:
        merged["start_year"] = merged["start_year"].astype("Int64")
        merged["end_year"] = merged["end_year"].astype("Int64")

    # Sort alphabetically by university name for clean browsing
    merged = merged[["university_name", "root_url", "start_year", "end_year"]].sort_values("university_name").reset_index(drop=True)

    return merged


def create_subpaths_table(
    data: pd.DataFrame | dict[str, list[str] | set[str]] | None = None,
    university_name: str | None = None,
    urls: list[str] | set[str] | None = None,
    max_depth: int = 3,
    max_pages: int = 50,
    keywords: list[str] | None = None,
    concurrency: int = 10,
    timeout: int = 10,
    limit: int | None = None,
    show_progress: bool = True,
) -> pd.DataFrame:
    """
    Produce a table mapping each university to its crawled subpaths,
    with a 'relevant' flag defaulting to False.

    Accepts:
      - `unique_universities_df`: DataFrame containing 'university_name' and 'root_url'.
        It will crawl each university's root URL up to `max_depth` and `max_pages`.
      - A DataFrame that already has a crawled URLs column ('crawled_urls' / 'urls' / 'crawled_url').
        It will explode and convert to subpaths without re-crawling.
      - A dictionary mapping university names to lists/sets of URLs.
      - Direct arguments `(university_name="Harvard", urls=["https://..."])`.

    Args:
        data: DataFrame (such as unique_universities_df) or dict of URLs.
        university_name: Optional single university name when passing `urls` directly.
        urls: Optional list or set of URLs when passing a single university name.
        max_depth: Maximum depth for the crawler when crawling root URLs (default 3).
        max_pages: Maximum pages to visit per university (default 50).
        keywords: Optional keywords list to filter crawled links.
        concurrency: Max simultaneous HTTP requests per site.
        timeout: Request timeout in seconds.
        limit: Optional row limit when crawling universities (e.g. limit=10).
        show_progress: Whether to show a progress bar when crawling multiple universities.

    Returns:
        pd.DataFrame with columns:
            - 'university_name': Name of the university
            - 'subpaths': The relative subpath (e.g. '/careers/resume-tips')
            - 'relevant': Boolean flag (defaults to False for all rows)
    """
    records: list[dict] = []

    # Case 1: Direct university_name + urls list passed
    if university_name is not None and urls is not None:
        for u in urls:
            records.append({
                "university_name": university_name,
                "subpaths": _extract_subpath(u),
                "relevant": False,
            })
        return pd.DataFrame(records, columns=["university_name", "subpaths", "relevant"]).drop_duplicates().reset_index(drop=True)

    # Case 2: Dict of {university_name: [urls]}
    if isinstance(data, dict):
        for name, url_list in data.items():
            for u in url_list:
                records.append({
                    "university_name": name,
                    "subpaths": _extract_subpath(u),
                    "relevant": False,
                })
        return pd.DataFrame(records, columns=["university_name", "subpaths", "relevant"]).drop_duplicates().reset_index(drop=True)

    # Case 3: pandas DataFrame (e.g. unique_universities_df)
    if isinstance(data, pd.DataFrame):
        if data.empty:
            return pd.DataFrame(columns=["university_name", "subpaths", "relevant"])

        df = data.copy()
        df.columns = df.columns.str.strip().str.lower()

        # Identify university name column
        name_col = next(
            (c for c in ["university_name", "university name", "instnm", "name"] if c in df.columns),
            None,
        )
        if not name_col:
            raise KeyError(
                f"Could not find university name column in DataFrame. Available columns: {list(df.columns)}"
            )

        # Check if a pre-crawled list/set of URLs exists in the DataFrame
        crawled_col = next(
            (
                c
                for c in [
                    "crawled_url",
                    "crawled_urls",
                    "urls",
                    "subpath",
                    "subpaths",
                    "results",
                    "link",
                ]
                if c in df.columns
            ),
            None,
        )

        if crawled_col:
            # Already crawled -> explode and extract subpaths
            exploded = df[[name_col, crawled_col]].explode(crawled_col).dropna(subset=[crawled_col])
            exploded["university_name"] = exploded[name_col]
            exploded["subpaths"] = exploded[crawled_col].apply(_extract_subpath)
            exploded["relevant"] = False
            return (
                exploded[["university_name", "subpaths", "relevant"]]
                .drop_duplicates()
                .reset_index(drop=True)
            )

        # If no pre-crawled column, look for root_url / webaddr to crawl
        root_col = next(
            (c for c in ["root_url", "root url", "webaddr", "web_addr", "website", "url"] if c in df.columns),
            None,
        )
        if not root_col:
            raise KeyError(
                f"Could not find 'root_url' or crawled URLs column in DataFrame. Available columns: {list(df.columns)}"
            )

        # Crawl each university's root URL
        df_to_crawl = df if limit is None else df.head(limit)
        iterator = df_to_crawl.itertuples()
        if show_progress:
            try:
                from tqdm.auto import tqdm
                iterator = tqdm(iterator, total=len(df_to_crawl), desc="Crawling universities")
            except ImportError:
                pass

        for row in iterator:
            name = getattr(row, name_col)
            root_url = getattr(row, root_col)
            if not root_url or pd.isna(root_url):
                continue

            try:
                found_urls = crawl(
                    str(root_url),
                    max_depth=max_depth,
                    max_pages=max_pages,
                    keywords=keywords,
                    concurrency=concurrency,
                    timeout=timeout,
                )
            except Exception:
                found_urls = set()

            if found_urls:
                for u in found_urls:
                    records.append({
                        "university_name": name,
                        "subpaths": _extract_subpath(u),
                        "relevant": False,
                    })

        res = pd.DataFrame(records, columns=["university_name", "subpaths", "relevant"])
        return res.drop_duplicates().reset_index(drop=True)

    # Default empty DataFrame
    return pd.DataFrame(columns=["university_name", "subpaths", "relevant"])
