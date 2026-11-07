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
    links: list[str] = Field(
        default_factory=list,
        description="List of source URLs or repositories searched/crawled for this experience."
    )
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

    links = [u for u in [devpost_data.get("url"), devpost_data.get("github_url"), devpost_data.get("demo_url")] if u]

    return Experience(
        label=title,
        type="project",
        start_date="",
        end_date="",
        location="Remote",
        links=links,
        skills=built_with,
        context="\n\n".join(context_parts)
    )


class LLMContextSynthesis(BaseModel):
    skills: list[str] = Field(
        ...,
        description="Comprehensive list of technical skills, programming languages, libraries, frameworks, cloud/devops tools, and APIs used in this project."
    )
    context: str = Field(
        ...,
        description=(
            "Exhaustive, deep technical narrative paragraph (at least 250 words, longer as needed to preserve all depth) "
            "explaining what the project is, the architecture, technologies and ML models/engines used, data flows, and grounded metrics. "
            "Never refer to 'the document' or 'the README'. Strictly NO bullet points or bullet symbols."
        )
    )


def devpost_to_experience_llm(
    url_or_data: str | dict[str, Any],
    model_name: str = "gemma3:12b",
    num_ctx: int = 32_768,
    num_predict: int = 4096,
    token: str | None = None,
) -> Experience:
    """
    Extract Devpost project (and recursively inspect its linked GitHub repository if available)
    and use Pydantic structured output to populate the experience fields, skills list,
    and dense narrative context.
    """
    try:
        from helpers.devpost_parser import get_devpost_project
    except ImportError:
        from devpost_parser import get_devpost_project

    from langchain_ollama import ChatOllama

    data = get_devpost_project(url_or_data) if isinstance(url_or_data, str) else url_or_data

    if "error" in data:
        raise RuntimeError(f"Failed to scrape Devpost URL: {data['error']}")

    title = data.get("title", "Project")
    built_with_list = data.get("built_with", [])
    built_with_str = ", ".join(built_with_list) if built_with_list else "None tagged"
    awards_str = ", ".join(data.get("awards", [])) if data.get("awards") else "None"
    hackathons_str = ", ".join(data.get("hackathons", [])) if data.get("hackathons") else "None"
    description_text = data.get("description", "").strip() or data.get("tagline", "")

    # Recursively inspect linked GitHub repository if link is available
    github_data: dict[str, Any] | None = None
    start_date = ""
    end_date = ""
    github_url = data.get("github_url", "")

    if github_url and "github.com" in github_url:
        try:
            from helpers.github_parser import get_recursive_github_repo
            github_data = get_recursive_github_repo(
                github_url,
                max_files=16,
                max_file_chars=3500,
                token=token,
            )
            if github_data and "metadata" in github_data:
                start_date = github_data["metadata"].get("start_date", "")
                end_date = github_data["metadata"].get("end_date", "")
        except Exception:
            github_data = None

    extractor = ChatOllama(
        model=model_name,
        temperature=0.1,
        num_ctx=num_ctx,
        num_predict=num_predict,
    ).with_structured_output(LLMContextSynthesis)

    # Base prompt with Devpost story
    prompt = f"""You are an expert technical architect and systems engineer.
Synthesize the Devpost project{' and its linked GitHub repository' if github_data else ''} for '{title}' into an exhaustive, deep technical narrative and extract all skills.

OUTPUT FORMAT INSTRUCTIONS:
- 'skills': A comprehensive list of all technical skills, programming languages, libraries, frameworks, cloud/devops tools, and APIs used (combining Devpost tags and codebase dependencies).
- 'context': A continuous, multi-sentence, highly detailed technical narrative paragraph (at least 250-500+ words).

NARRATIVE OBJECTIVES FOR 'context':
1. WHAT THE PROJECT IS: Clearly state what '{title}' is, its core purpose, domain problem, and the functionality it provides to users.
2. TECHNOLOGIES & ARCHITECTURE: Detail the tech stack and system architecture:
   - Frontend frameworks, UI libraries, reactive state management, and user interaction (e.g. Svelte, TypeScript).
   - Backend architecture, microservices, frameworks, and APIs (e.g. FastAPI, Python).
   - Artificial intelligence & machine learning models and engine integrations (e.g. Maia-3 chess model, custom MLP neural network adapters, move evaluation pipelines, LLMs).
   - Databases, storage, and persistence layers (e.g. SQLite, PostgreSQL, SQL).
   - Containerization and deployment (e.g. Docker, single-command orchestration).
3. HOW IT WORKS: Detail how data flows end-to-end through the system (e.g. Chess.com PGN ingestion -> move snapshot evaluation -> MLP clone model training/scoring -> interactive in-game replay -> AI commentary).
4. GROUNDED METRICS: Integrate real metrics explicitly documented in Devpost (e.g. ~60% accuracy outperforming baseline Maia model, rapid/blitz game support, training over hundreds of games, team size of {len(data.get('team', []))}){' and GitHub (' + str(github_data.get('total_files', 0)) + ' source files in tree)' if github_data else ''}. Never fabricate numbers.
5. STRICT CONSTRAINT: Do NOT use bullet points or bullet symbols. Write a continuous, cohesive paragraph. Talk about the project directly; never say 'The document describes...' or 'The submission outlines...'.

PROJECT METADATA:
- Project Name: {title}
- Tagline: {data.get('tagline', '')}
- Technologies Tagged: {built_with_str}
- Awards Won: {awards_str}
- Hackathons: {hackathons_str}
{f"- Active Timeline: {start_date} to {end_date}" if start_date else ""}

DEVPOST PROJECT STORY & BACKGROUND:
{description_text}
"""

    # If GitHub was recursively inspected, enrich with directory tree and key files
    if github_data:
        gh_meta = github_data.get("metadata", {})
        gh_files_read = github_data.get("files_read", list(github_data.get("key_files", {}).keys()))
        gh_key_files_str = "\n\n".join(
            f"=== FILE: {p} ===\n{c}" for p, c in github_data.get("key_files", {}).items()
        )
        prompt += f"""
LINKED GITHUB REPOSITORY CODEBASE ({github_url}):
- Languages Breakdown: {', '.join(gh_meta.get('languages', []))}
- Repository Scale: {github_data.get('total_files', len(gh_files_read))} source files in tree
- GitHub Stars / Forks: {gh_meta.get('stars', 0)} stars, {gh_meta.get('forks', 0)} forks

GITHUB REPOSITORY FILE TREE:
{github_data.get('directory_tree', 'N/A')}

KEY CODE & MANIFEST FILES ({len(gh_files_read)} files inspected: {', '.join(gh_files_read)}):
{gh_key_files_str if gh_key_files_str else 'No additional files fetched.'}
"""

    synthesis = extractor.invoke(prompt)

    raw_context = synthesis.context if hasattr(synthesis, "context") else str(synthesis)
    try:
        from helpers.github_parser import _clean_context_narrative
        cleaned_context = _clean_context_narrative(raw_context, title)
    except Exception:
        cleaned_context = raw_context

    extracted_skills = synthesis.skills if hasattr(synthesis, "skills") and synthesis.skills else built_with_list

    searched_links: list[str] = []
    if data.get("url"):
        searched_links.append(data["url"])
    if github_url and github_url not in searched_links:
        searched_links.append(github_url)
    if data.get("demo_url") and data["demo_url"] not in searched_links:
        searched_links.append(data["demo_url"])

    return Experience(
        label=title,
        type="project",
        start_date=start_date,
        end_date=end_date,
        location="Remote",
        links=searched_links,
        skills=extracted_skills,
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

