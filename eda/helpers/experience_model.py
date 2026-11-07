"""
experience_model.py

Standard 6-field experience schema and conversion utilities.
Fields: label, type, start_date, end_date, location, context.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class Experience(BaseModel):
    """
    Standard experience format containing the 6 core fields:
    label, type, start_date, end_date, location, context.
    """
    label: str = Field(..., description="Short title, role name, or project identifier (e.g. 'Software Engineering Intern')")
    type: str = Field(..., description="Category (e.g. 'work', 'project', 'research', 'leadership', 'education')")
    start_date: str = Field("", description="Start date (e.g. '2025-05' or 'May 2025')")
    end_date: str = Field("", description="End date (e.g. '2025-08', 'August 2025', or 'Present')")
    location: str = Field("", description="Location (e.g. 'San Francisco, CA' or 'Remote')")
    context: str = Field("", description="Full text descriptions, role context, company narrative, and bullet points")

    def to_json(self, indent: int = 2) -> str:
        """Export as a formatted JSON string."""
        return self.model_dump_json(indent=indent)

    def to_dict(self) -> dict[str, Any]:
        """Export as a Python dictionary."""
        return self.model_dump()


def from_devpost(devpost_data: dict[str, Any]) -> Experience:
    """
    Convert a Devpost project dictionary into the 6-field Experience format.
    """
    title = devpost_data.get("title", "Devpost Project")
    tagline = devpost_data.get("tagline", "")
    hackathons = ", ".join(devpost_data.get("hackathons", []))
    built_with = ", ".join(devpost_data.get("built_with", []))
    awards = ", ".join(devpost_data.get("awards", []))
    description = devpost_data.get("description", "")

    # Combine narrative details into the context block
    context_parts = []
    if hackathons:
        context_parts.append(f"Hackathon: {hackathons}")
    if tagline:
        context_parts.append(f"Tagline: {tagline}")
    if built_with:
        context_parts.append(f"Built With: {built_with}")
    if awards:
        context_parts.append(f"Awards: {awards}")
    if description:
        context_parts.append(f"Description:\n{description}")

    return Experience(
        label=title,
        type="project",
        start_date="",
        end_date="",
        location="Remote",
        context="\n\n".join(context_parts)
    )
