"""
github_parser.py

Helper module to extract project metadata, recursive directory trees,
and key code files from GitHub repositories, and summarize them into
standardized Experience objects via local LLMs.
"""

from __future__ import annotations

import base64
import fnmatch
import re
from typing import Any
from urllib.parse import urlparse

import requests
from pydantic import BaseModel, Field

_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "application/vnd.github.v3+json",
}

IGNORE_DIRS = {
    ".git", ".github", "node_modules", "dist", "build", "out", "target",
    "venv", ".venv", "env", ".env", "__pycache__", ".pytest_cache",
    ".next", ".nuxt", ".cache", ".idea", ".vscode", "coverage", "vendor",
    "pods", "deriveddata", "wheels"
}

IGNORE_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".mp4",
    ".mp3", ".wav", ".zip", ".tar", ".gz", ".7z", ".pdf", ".bin", ".exe",
    ".pyc", ".pyo", ".wasm", ".dylib", ".so", ".dll", ".otf", ".ttf",
    ".woff", ".woff2", ".eot", ".map", ".lock", ".csv", ".tsv", ".sqlite",
    ".db", ".pkl", ".parquet", ".feather", ".h5", ".onnx", ".pt", ".pth"
}

IGNORE_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "cargo.lock", "gemfile.lock", "composer.lock", "tags"
}

MANIFEST_FILES = {
    "package.json", "pyproject.toml", "requirements.txt", "setup.py",
    "cargo.toml", "go.mod", "pom.xml", "build.gradle", "dockerfile",
    "docker-compose.yml", "docker-compose.yaml", "makefile", "gemfile",
    "svelte.config.js", "svelte.config.ts", "vite.config.js", "vite.config.ts",
    "tsconfig.json", "next.config.js", "next.config.mjs", "nuxt.config.ts",
    "tailwind.config.js", "tailwind.config.ts"
}

ENTRYPOINT_PATTERNS = [
    "main.*", "app.*", "index.*", "server.*", "cli.*", "manage.py",
    "api.*", "core.*", "lib.*", "engine.*", "model.*", "models.*",
    "+page.svelte", "+page.server.ts", "+server.ts", "+layout.svelte",
    "+layout.server.ts", "hooks.server.ts", "router.*", "routes.*"
]

CODE_EXTS = {
    ".py", ".ts", ".js", ".svelte", ".vue", ".astro", ".tsx", ".jsx",
    ".mjs", ".cjs", ".go", ".rs", ".java", ".cpp", ".c", ".h", ".hpp",
    ".cs", ".rb", ".php", ".swift", ".kt", ".scala", ".sql", ".prisma",
    ".graphql"
}

DEFAULT_MAX_README_CHARS = 120_000
DEFAULT_NUM_CTX = 32_768
DEFAULT_NUM_PREDICT = 4096


class LLMRepoSynthesis(BaseModel):
    """Structured LLM extraction target focused purely on skills and context synthesis."""
    skills: list[str] = Field(
        description="Comprehensive list of technical skills, languages, frameworks, UI libraries, engines, APIs, databases, and devops tools used in this codebase."
    )
    context: str = Field(
        description=(
            "Exhaustive, deep technical narrative paragraph (at least 250 words, longer as needed to fully capture all depth) describing what the project is, "
            "its architecture, the specific technologies and ML models/engines used, data flows, and relevant codebase metrics. "
            "Never refer to 'the document' or 'the README'. Strictly NO bullet points or bullet symbols."
        )
    )


def _clean_context_narrative(context: str, repo_name: str) -> str:
    """Clean whitespace while preserving the model's full natural phrasing."""
    return re.sub(r"\s{2,}", " ", context).strip()


def _parse_github_url(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub repository URL."""
    clean = str(url).strip().rstrip("/")
    if clean.endswith(".git"):
        clean = clean[:-4]

    parsed = urlparse(clean if clean.startswith("http") else f"https://{clean}")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub repository URL: {url}")
    return parts[0], parts[1]


def _get_headers(token: str | None = None) -> dict[str, str]:
    headers = dict(_DEFAULT_HEADERS)
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def get_github_repo(
    url: str,
    timeout: int = 10,
    token: str | None = None,
    max_readme_chars: int = DEFAULT_MAX_README_CHARS,
) -> dict[str, Any]:
    """
    Fetch repository metadata, tech stack, dates, metrics, and README content
    for any public GitHub repository.
    """
    owner, repo = _parse_github_url(url)
    headers = _get_headers(token)
    api_base = f"https://api.github.com/repos/{owner}/{repo}"

    # 1. Fetch Repository Metadata
    resp = requests.get(api_base, headers=headers, timeout=timeout)
    resp.raise_for_status()
    repo_data = resp.json()

    # 2. Extract Languages with percentage metrics
    languages: list[str] = []
    try:
        lang_resp = requests.get(f"{api_base}/languages", headers=headers, timeout=timeout)
        if lang_resp.status_code == 200:
            lang_dict = lang_resp.json()
            total_b = sum(lang_dict.values())
            if total_b > 0:
                languages = [
                    f"{lang} ({round(cnt / total_b * 100, 1)}%)"
                    for lang, cnt in sorted(lang_dict.items(), key=lambda x: x[1], reverse=True)
                ]
            else:
                languages = list(lang_dict.keys())
    except Exception:
        pass

    # 3. Fetch README Content
    readme_text = ""
    try:
        readme_resp = requests.get(f"{api_base}/readme", headers=headers, timeout=timeout)
        if readme_resp.status_code == 200:
            readme_json = readme_resp.json()
            content_b64 = readme_json.get("content", "")
            readme_text = base64.b64decode(content_b64).decode("utf-8", errors="replace")
    except Exception:
        for branch in [repo_data.get("default_branch", "main"), "main", "master"]:
            try:
                raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md"
                r = requests.get(raw_url, timeout=timeout)
                if r.status_code == 200:
                    readme_text = r.text
                    break
            except Exception:
                pass

    # Extract clean YYYY-MM dates from GitHub commit history
    created_at = (repo_data.get("created_at") or "")[:7]
    pushed_at = (repo_data.get("pushed_at") or "")[:7]

    clean_readme = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)", "", readme_text)
    clean_readme = re.sub(r"\n{3,}", "\n\n", clean_readme).strip()

    return {
        "name": repo_data.get("name", repo),
        "owner": owner,
        "url": repo_data.get("html_url", f"https://github.com/{owner}/{repo}"),
        "default_branch": repo_data.get("default_branch", "main"),
        "description": repo_data.get("description", "") or "",
        "topics": repo_data.get("topics", []),
        "languages": languages,
        "stars": repo_data.get("stargazers_count", 0),
        "forks": repo_data.get("forks_count", 0),
        "start_date": created_at,
        "end_date": pushed_at,
        "homepage": repo_data.get("homepage", "") or "",
        "readme_text": clean_readme[:max_readme_chars] if max_readme_chars else clean_readme,
    }


def fetch_file_content(
    owner: str,
    repo: str,
    path: str,
    branch: str = "main",
    token: str | None = None,
    max_chars: int = 4000,
    timeout: int = 10,
) -> str:
    """
    Fetch text content of a single file from GitHub via raw.githubusercontent.com
    with fallback to GitHub Contents API. Tries multiple branches if necessary.
    """
    raw_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Accept": "*/*",
    }
    if token:
        raw_headers["Authorization"] = f"token {token}"

    branches_to_try = [branch]
    for fallback in ["main", "master"]:
        if fallback not in branches_to_try:
            branches_to_try.append(fallback)

    # 1. Try raw endpoint
    for b in branches_to_try:
        try:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{b}/{path}"
            r = requests.get(raw_url, headers=raw_headers, timeout=timeout)
            if r.status_code == 200 and r.text:
                return r.text[:max_chars]
        except Exception:
            pass

    # 2. Fallback to GitHub Contents API
    api_headers = _get_headers(token)
    for b in branches_to_try:
        try:
            api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={b}"
            r = requests.get(api_url, headers=api_headers, timeout=timeout)
            if r.status_code == 200:
                content_b64 = r.json().get("content", "")
                if content_b64:
                    return base64.b64decode(content_b64).decode("utf-8", errors="replace")[:max_chars]
        except Exception:
            pass

    return ""


def _select_representative_files(file_paths: list[str], max_files: int = 16) -> list[str]:
    """
    Select a diverse, highly informative set of files across manifests, entrypoints,
    frontend routes/components, backend services, and domain logic.
    """
    manifests: list[str] = []
    entrypoints: list[str] = []
    subsystems: dict[str, list[str]] = {}

    for p in file_paths:
        fname = p.split("/")[-1].lower()
        if fname in MANIFEST_FILES:
            manifests.append(p)
            continue

        is_entry = any(fnmatch.fnmatch(fname, pat) for pat in ENTRYPOINT_PATTERNS)
        if is_entry:
            entrypoints.append(p)
            continue

        p_lower = p.lower()
        if any(p_lower.endswith(ext) for ext in CODE_EXTS):
            # Top folder grouping (e.g. frontend, backend, src, lib)
            top_folder = p.split("/")[0] if "/" in p else "root"
            subsystems.setdefault(top_folder, []).append(p)

    selected: list[str] = []

    # 1. Top manifests / build configs (up to 4)
    selected.extend(manifests[:4])

    # 2. Top entry points & routes (up to 6)
    selected.extend(entrypoints[:6])

    # 3. Round-robin from subsystem folders so frontend and backend are both sampled
    while len(selected) < max_files and any(subsystems.values()):
        for folder in list(subsystems.keys()):
            if len(selected) >= max_files:
                break
            if subsystems[folder]:
                selected.append(subsystems[folder].pop(0))

    # Deduplicate while preserving order
    seen = set()
    result = []
    for item in selected:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result[:max_files]


def format_directory_tree(paths: list[str], max_lines: int = 60) -> str:
    """Generate a clean ASCII directory tree from a list of relative paths."""
    tree: dict[str, Any] = {}
    for p in paths:
        parts = p.split("/")
        curr = tree
        for part in parts:
            curr = curr.setdefault(part, {})

    lines: list[str] = []

    def _render(node: dict[str, Any], prefix: str = ""):
        if len(lines) >= max_lines:
            return
        keys = sorted(node.keys(), key=lambda k: (len(node[k]) == 0, k.lower()))
        for i, k in enumerate(keys):
            if len(lines) >= max_lines:
                lines.append(f"{prefix}... [truncated {len(paths) - max_lines} more files]")
                return
            is_last = (i == len(keys) - 1)
            branch = "└── " if is_last else "├── "
            child_prefix = "    " if is_last else "│   "
            lines.append(f"{prefix}{branch}{k}")
            if node[k]:
                _render(node[k], prefix + child_prefix)

    _render(tree)
    return "\n".join(lines)


def get_recursive_github_repo(
    url: str,
    query: str | None = None,
    max_files: int = 16,
    max_file_chars: int = 4000,
    token: str | None = None,
    timeout: int = 15,
    max_readme_chars: int = DEFAULT_MAX_README_CHARS,
) -> dict[str, Any]:
    """
    Recursively inspect an entire GitHub repository:
    1. Fetches repo metadata & branches.
    2. Retrieves the complete recursive Git tree via GitHub Trees API.
    3. Filters out vendor dirs, binaries, and lockfiles.
    4. Selects a diverse cross-section of manifests, entrypoints, and frontend/backend files.
    5. Fetches source content of selected files.
    """
    owner, repo = _parse_github_url(url)
    repo_meta = get_github_repo(url, timeout=timeout, token=token, max_readme_chars=max_readme_chars)
    branch = repo_meta.get("default_branch", "main")
    headers = _get_headers(token)

    # Fetch recursive Git Tree
    tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    tree_resp = requests.get(tree_url, headers=headers, timeout=timeout)

    file_paths: list[str] = []
    if tree_resp.status_code == 200:
        raw_tree = tree_resp.json().get("tree", [])
        for item in raw_tree:
            if item.get("type") != "blob":
                continue
            path = item.get("path", "")
            parts = path.split("/")

            if any(part in IGNORE_DIRS for part in parts[:-1]):
                continue

            fname_lower = parts[-1].lower()
            if fname_lower in IGNORE_FILENAMES:
                continue

            if any(fname_lower.endswith(ext) for ext in IGNORE_EXTS):
                continue

            if query and query.lower() not in path.lower():
                continue

            file_paths.append(path)

    tree_display = format_directory_tree(file_paths) if file_paths else "No matching files discovered."

    # Select representative files across the repository
    candidate_paths = _select_representative_files(file_paths, max_files=max_files)

    selected_files: dict[str, str] = {}
    for p in candidate_paths:
        if "readme" in p.lower() and repo_meta.get("readme_text"):
            continue
        content = fetch_file_content(
            owner, repo, p, branch=branch, token=token, max_chars=max_file_chars, timeout=timeout
        )
        if content.strip():
            selected_files[p] = content

    return {
        "metadata": repo_meta,
        "total_files": len(file_paths),
        "directory_tree": tree_display,
        "files_read": list(selected_files.keys()),
        "key_files": selected_files,
    }


def github_to_experience_llm(
    url_or_data: str | dict[str, Any],
    model_name: str = "gemma3:12b",
    recursive: bool = True,
    max_files: int = 16,
    token: str | None = None,
    num_ctx: int = DEFAULT_NUM_CTX,
    num_predict: int = DEFAULT_NUM_PREDICT,
    max_readme_chars: int = DEFAULT_MAX_README_CHARS,
) -> Any:
    """
    Extract GitHub repository details and use Ollama + Gemma 3 12B to synthesize
    an exhaustive technical context paragraph and comprehensive skills list,
    combining them with ground-truth repository metadata into the Experience schema.
    """
    try:
        from helpers.experience_model import Experience
    except ImportError:
        from experience_model import Experience

    from langchain_ollama import ChatOllama

    if isinstance(url_or_data, str):
        if recursive:
            data = get_recursive_github_repo(
                url_or_data, max_files=max_files, token=token, max_readme_chars=max_readme_chars
            )
        else:
            data = {"metadata": get_github_repo(url_or_data, token=token, max_readme_chars=max_readme_chars), "key_files": {}}
    else:
        data = url_or_data

    repo_meta = data.get("metadata", data)
    repo_name = repo_meta.get("name", "Project")
    files_read = data.get("files_read", list(data.get("key_files", {}).keys()))

    key_files_str = "\n\n".join(
        f"=== FILE: {path} ===\n{content}" for path, content in data.get("key_files", {}).items()
    )

    prompt = f"""You are an expert technical architect and systems engineer.
Synthesize the provided codebase and architecture for '{repo_name}' into an exhaustive, deep technical narrative.

NARRATIVE STRUCTURE & OBJECTIVES:
1. WHAT THE PROJECT IS: Explain what '{repo_name}' is, its core purpose, domain problem, and the capabilities it provides to users.
2. TECHNOLOGIES & ARCHITECTURE IN DEPTH: Go into technical detail on the stack and systems:
   - Frontend frameworks, UI libraries, reactive state management, and routing (e.g. SvelteKit, TypeScript).
   - Backend architecture, microservices, frameworks, and APIs (e.g. FastAPI, Node, WebSocket, REST).
   - AI/ML models, algorithms, and engine integrations (e.g. Maia-3, Gemma via llama.cpp, custom MLP adapters, pgvector embeddings).
   - Databases, schemas, vector storage, and caching layers.
   - Containerization, orchestration, and infrastructure (e.g. Docker Compose, standalone CLI tools, test suites).
3. HOW IT WORKS END-TO-END: Describe how data and requests flow through the system (e.g. game input -> model evaluation -> embedding similarity -> commentary generation -> client response).
4. RELEVANT CODE METRICS: Include factually grounded numbers (e.g. {data.get('total_files', len(files_read))} source files across tree, language breakdown: {', '.join(repo_meta.get('languages', []))}, timeline: {repo_meta.get('start_date', '')} to {repo_meta.get('end_date', '')}, or code constants/benchmarks explicitly in the source). Never invent fake statistics.

CRITICAL PRESENTATION RULES:
- Focus on the SOFTWARE and the PROJECT itself.
- NEVER talk about the text or files as 'the document', 'the README', 'the paper', or 'the text' (e.g. do NOT say 'The document describes...', 'The README details...', 'The document covers...', 'The repository structure is described...'). Start directly by describing what '{repo_name}' is.
- STRICT CONSTRAINT: Do NOT use bullet points, bullet symbols, or dashes. Write a continuous, cohesive, multi-sentence technical narrative paragraph (at least 250-500+ words, longer if necessary to capture all architectural depth and metrics without artificial truncation).

GROUND RULES FOR 'skills':
- Extract all programming languages, frameworks, libraries, databases, devops tools, and APIs used across the project (e.g. FastAPI, SvelteKit, TypeScript, PostgreSQL, pgvector, Docker Compose, llama.cpp, Maia-3, etc.).

REPOSITORY METADATA:
- Project Name: {repo_name}
- Tagline/Description: {repo_meta.get('description', '')}
- Primary Languages: {', '.join(repo_meta.get('languages', []))}
- Active Development Timeline: {repo_meta.get('start_date', '')} to {repo_meta.get('end_date', '')}
- Codebase Scale: {data.get('total_files', len(files_read))} source files across tree

REPOSITORY ARCHITECTURE & CODEBASE:
{data.get('directory_tree', 'N/A')}

KEY SOURCE CODE AND CONFIGURATION FILES ({len(files_read)} files inspected):
{key_files_str if key_files_str else 'No additional source files.'}

TECHNICAL SPECIFICATION & OVERVIEW:
{repo_meta.get('readme_text', 'No technical overview provided')}
"""

    extractor = ChatOllama(
        model=model_name,
        temperature=0.1,
        num_ctx=num_ctx,
        num_predict=num_predict,
    ).with_structured_output(LLMRepoSynthesis)

    synthesis = extractor.invoke(prompt)

    raw_context = synthesis.context if hasattr(synthesis, "context") else str(synthesis)
    cleaned_context = _clean_context_narrative(raw_context, repo_name)

    repo_url = repo_meta.get("url") or repo_meta.get("html_url") or ""
    links = [repo_url] if repo_url else []
    homepage = repo_meta.get("homepage")
    if homepage and homepage not in links:
        links.append(homepage)

    # Combine ground-truth metadata with the LLM's skills and deep technical context
    return Experience(
        label=repo_name,
        type="project",
        start_date=repo_meta.get("start_date", ""),
        end_date=repo_meta.get("end_date", ""),
        location="Remote",
        links=links,
        skills=synthesis.skills if hasattr(synthesis, "skills") else [],
        context=cleaned_context,
    )


def recursively_summarize_github_repo(
    url: str,
    model_name: str = "gemma3:12b",
    query: str | None = None,
    max_files: int = 16,
    token: str | None = None,
    num_ctx: int = DEFAULT_NUM_CTX,
    num_predict: int = DEFAULT_NUM_PREDICT,
    max_readme_chars: int = DEFAULT_MAX_README_CHARS,
) -> Any:
    """
    Recursively traverses the entire GitHub repository, retrieves directory structure
    and key source files (optionally filtered by query), and summarizes the codebase into
    an Experience object using a local Ollama LLM.
    """
    repo_data = get_recursive_github_repo(
        url, query=query, max_files=max_files, token=token, max_readme_chars=max_readme_chars
    )
    return github_to_experience_llm(
        repo_data,
        model_name=model_name,
        num_ctx=num_ctx,
        num_predict=num_predict,
        max_readme_chars=max_readme_chars,
    )
