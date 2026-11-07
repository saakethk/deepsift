"""
devpost_parser.py

Helper module to extract project information from Devpost project URLs.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
import pandas as pd

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def get_devpost_project(url: str, timeout: int = 10) -> dict[str, Any]:
    """
    Scrape and extract structured project information from a Devpost project URL.

    Args:
        url: Full Devpost project URL (e.g. 'https://devpost.com/software/my-project').
        timeout: Request timeout in seconds.

    Returns:
        dict containing:
            - 'url': The canonical project URL
            - 'title': Project name
            - 'tagline': One-line pitch / subtitle
            - 'description': Full project description / story
            - 'built_with': List of technologies used
            - 'team': List of dicts with member 'name' and 'profile' link
            - 'github_url': Primary GitHub repository link (if available)
            - 'demo_url': Try-it-out / demo link (if available)
            - 'awards': List of prizes / winning categories
            - 'hackathons': List of hackathons the project was submitted to
    """
    clean_url = str(url).strip()
    if not clean_url.startswith(("http://", "https://")):
        clean_url = f"https://{clean_url}"

    parsed = urlparse(clean_url)
    if "devpost.com" not in parsed.netloc:
        raise ValueError(f"URL does not appear to be a Devpost link: {clean_url}")

    result: dict[str, Any] = {
        "url": clean_url,
        "title": "",
        "tagline": "",
        "description": "",
        "built_with": [],
        "team": [],
        "github_url": "",
        "demo_url": "",
        "awards": [],
        "hackathons": [],
    }

    try:
        resp = requests.get(clean_url, headers=_DEFAULT_HEADERS, timeout=timeout)
        resp.raise_for_status()
    except Exception as e:
        result["error"] = str(e)
        return result

    soup = BeautifulSoup(resp.text, "html.parser")

    # 1. Project Title
    title_tag = soup.find("h1", id="app-title")
    if not title_tag:
        title_tag = soup.find("h1")
    result["title"] = title_tag.get_text(strip=True) if title_tag else ""

    # 2. Tagline
    tagline_tag = soup.find("p", class_="large")
    if not tagline_tag:
        # Fallback to OpenGraph description
        og_desc = soup.find("meta", property="og:description")
        result["tagline"] = og_desc.get("content", "").strip() if og_desc else ""
    else:
        result["tagline"] = tagline_tag.get_text(strip=True)

    # 3. Built With (Technologies)
    built_with: list[str] = []
    built_with_header = soup.find(lambda t: t.name in ["h5", "h4", "h3"] and "built with" in t.text.lower())
    if built_with_header:
        ul_tag = built_with_header.find_next(["ul", "ol"])
        if ul_tag:
            for li in ul_tag.find_all("li"):
                text = li.get_text(strip=True)
                if text:
                    built_with.append(text)
    # Fallback to .cp-tag or .facet elements
    if not built_with:
        for tag in soup.select("span.cp-tag"):
            t = tag.get_text(strip=True)
            if t and t not in built_with:
                built_with.append(t)
    result["built_with"] = built_with

    # 4. Links (GitHub & Live Demo)
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(strip=True).lower()
        if "github.com" in href and not result["github_url"]:
            # Filter out devpost's own github links if any
            if "/software" not in href:
                result["github_url"] = href
        elif any(k in text for k in ["try it out", "live demo", "website", "app"]):
            if not result["demo_url"] and not href.startswith("#"):
                result["demo_url"] = href

    # 5. Team Members
    team: list[dict[str, str]] = []
    for user_li in soup.select("li.bubble, .user-profile-link"):
        a_tag = user_li.find("a", href=True) if user_li.name != "a" else user_li
        if a_tag:
            name = a_tag.get_text(strip=True)
            profile = a_tag["href"]
            if profile.startswith("/"):
                profile = f"https://devpost.com{profile}"
            if name and not any(m["name"] == name for m in team):
                team.append({"name": name, "profile": profile})
    result["team"] = team

    # 6. Awards / Wins
    awards: list[str] = []
    for badge in soup.find_all(class_=re.compile(r"winner|winner-badge", re.IGNORECASE)):
        parent = badge.find_parent(["li", "div"])
        if parent:
            text = parent.get_text(separator=" - ", strip=True)
            if text and text not in awards:
                awards.append(text)
    result["awards"] = awards

    # 7. Hackathons Submitted To
    hackathons: list[str] = []
    submissions_section = soup.find("section", id="submissions") or soup.find(class_="submissions")
    if submissions_section:
        for a in submissions_section.find_all("a", href=True):
            h_name = a.get_text(strip=True)
            if h_name and h_name not in hackathons and "devpost.com" in a["href"]:
                hackathons.append(h_name)
    result["hackathons"] = hackathons

    # 8. Full Description
    details_div = soup.find("div", id="app-details-left") or soup.find(id="app-details")
    if details_div:
        result["description"] = details_div.get_text(separator="\n", strip=True)

    return result


def get_devpost_projects(urls: list[str], timeout: int = 10, as_dataframe: bool = False) -> list[dict[str, Any]] | pd.DataFrame:
    """
    Scrape multiple Devpost project URLs and optionally return a pandas DataFrame.

    Args:
        urls: List of Devpost project URLs.
        timeout: Request timeout per project.
        as_dataframe: If True, returns results as a pd.DataFrame.

    Returns:
        List of dicts or a pandas DataFrame.
    """
    results = [get_devpost_project(u, timeout=timeout) for u in urls]
    if as_dataframe:
        return pd.DataFrame(results)
    return results
