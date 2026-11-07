"""
experience_model.py

Standardized experience schema and conversion utilities.
Fields: label, type, start_date, end_date, location, skills, context.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class Experience(BaseModel):
    label: str = Field(description="Project name or role title")
    type: str = Field("project", description="Category: project, work, research, leadership, education")
    start_date: str = Field("", description="Start date YYYY-MM if mentioned, else empty")
    end_date: str = Field("", description="End date YYYY-MM if mentioned, else empty")
    location: str = Field("Remote", description="City, State or Remote")
    skills: list[str] = Field(
        default_factory=list,
        description="List of technical skills, programming languages, frameworks, libraries, databases, devops tools, and APIs associated with this experience."
    )
    context: str = Field(
        description=(
            "Exhaustive, deep technical narrative paragraph explaining what the project is, the specific technologies "
            "and architecture used, how it functions end-to-end, and relevant grounded metrics about the code. "
            "Never refer to 'the document' or 'the README'. Strictly NO bullet points or bullet symbols."
        )
    )

    def to_json(self, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


def from_devpost(devpost_data: dict[str, Any]) -> Experience:
    """
    Convert a Devpost project dictionary into the Experience format without an LLM.
    """
    title = devpost_data.get("title", "Devpost Project")
    tagline = devpost_data.get("tagline", "")
    hackathons = ", ".join(devpost_data.get("hackathons", []))
    built_with = devpost_data.get("built_with", [])
    built_with_str = ", ".join(built_with)
    awards = ", ".join(devpost_data.get("awards", []))
    description = devpost_data.get("description", "")

    # Combine narrative details into the context block
    context_parts = []
    if hackathons:
        context_parts.append(f"Hackathon: {hackathons}")
    if tagline:
        context_parts.append(f"Tagline: {tagline}")
    if built_with_str:
        context_parts.append(f"Built With: {built_with_str}")
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
        skills=built_with,
        context="\n\n".join(context_parts)
    )


class LLMContextSynthesis(BaseModel):
    skills: list[str] = Field(default_factory=list, description="Technical skills, languages, frameworks, libraries, APIs, and tools used.")
    context: str = Field(
        description=(
            "Exhaustive, highly technical narrative paragraph (at least 250 words, longer as needed to preserve all depth) packed with active verbs. "
            "Only include factually grounded numerical metrics from the project data; strictly NO hallucinated or fabricated numbers. "
            "NO bullet points."
        )
    )


def devpost_to_experience_llm(
    url_or_data: str | dict[str, Any],
    model_name: str = "gemma3:12b",
    num_ctx: int = 32_768,
    num_predict: int = 4096,
) -> Experience:
    """
    Extract Devpost project and use Pydantic structured output to populate
    the experience fields, skills list, and dense narrative context.
    """
    try:
        from helpers.devpost_parser import get_devpost_project
    except ImportError:
        from devpost_parser import get_devpost_project

    from langchain_ollama import ChatOllama

    data = get_devpost_project(url_or_data) if isinstance(url_or_data, str) else url_or_data
    extractor = ChatOllama(
        model=model_name,
        temperature=0.1,
        num_ctx=num_ctx,
        num_predict=num_predict,
    ).with_structured_output(LLMContextSynthesis)

    prompt = (
        f"You are an expert technical architect and systems engineer.\n"
        f"Synthesize the project '{data.get('title', 'Project')}' into an exhaustive, deep technical narrative.\n\n"
        "Requirements:\n"
        "1. WHAT THE PROJECT IS: Clearly state what the project is, its core purpose, and functionality provided.\n"
        "2. TECHNOLOGIES & ARCHITECTURE: Go into technical depth on the stack, frameworks, ML models/APIs, databases, and infrastructure used.\n"
        "3. HOW IT WORKS: Detail how data flows end-to-end through the system.\n"
        "4. GROUNDED METRICS: Incorporate verified metrics from the data (e.g. awards, team size, documented dataset sizes, or benchmarks explicitly cited). Never fabricate numbers.\n"
        "5. CRITICAL: Talk directly about the project and software. NEVER say 'The document describes...', 'The submission details...', or 'This project was created...'.\n"
        "6. In 'skills', list all technical skills, programming languages, libraries, frameworks, cloud/devops tools, and APIs used.\n"
        "7. Strict constraint: Do NOT write bullet points or list markers under any circumstances. Write a continuous, cohesive paragraph (at least 250-500+ words, longer if necessary to capture all technical depth without artificial truncation).\n\n"
        f"Project Data:\n{data}"
    )

    synthesis = extractor.invoke(prompt)

    raw_context = synthesis.context if hasattr(synthesis, "context") else str(synthesis)
    try:
        from helpers.github_parser import _clean_context_narrative
        cleaned_context = _clean_context_narrative(raw_context, data.get("title", "Project"))
    except Exception:
        cleaned_context = raw_context

    return Experience(
        label=data.get("title", "Project"),
        type="project",
        start_date="",
        end_date="",
        location="Remote",
        skills=synthesis.skills if hasattr(synthesis, "skills") else data.get("built_with", []),
        context=cleaned_context,
    )


def github_to_experience_llm(
    url_or_data: str | dict[str, Any],
    model_name: str = "gemma3:12b",
    recursive: bool = True,
    max_files: int = 16,
    token: str | None = None,
    num_ctx: int = 32_768,
    num_predict: int = 4096,
) -> Experience:
    """
    Extract a GitHub repository (with recursive tree inspection) and use
    Pydantic structured output to populate the 6-field Experience model.
    """
    try:
        from helpers.github_parser import github_to_experience_llm as _gh_llm
    except ImportError:
        from github_parser import github_to_experience_llm as _gh_llm

    return _gh_llm(
        url_or_data=url_or_data,
        model_name=model_name,
        recursive=recursive,
        max_files=max_files,
        token=token,
        num_ctx=num_ctx,
        num_predict=num_predict,
    )

