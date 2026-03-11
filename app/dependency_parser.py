from __future__ import annotations

import base64
import json
import tomllib
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .github_client import parse_repo_url
from .models import DependencyMetrics
from .retry import RetryError, run_with_retry


class DependencyParserError(Exception):
    pass


def parse_requirements_text(requirements_text: str) -> list[str]:
    dependencies: list[str] = []

    for raw_line in requirements_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith(("-r", "--requirement", "-c", "--constraint", "-e", "--editable")):
            continue

        base = line.split(";", 1)[0].strip()
        for separator in ("==", ">=", "<=", "~=", "!=", ">", "<"):
            if separator in base:
                base = base.split(separator, 1)[0].strip()
                break

        if base:
            dependencies.append(base)

    # Deduplicate while preserving order.
    return list(dict.fromkeys(dependencies))


def parse_pyproject_text(pyproject_text: str) -> list[str]:
    try:
        data = tomllib.loads(pyproject_text)
    except tomllib.TOMLDecodeError as exc:
        raise DependencyParserError("Could not parse pyproject.toml") from exc

    dependencies: list[str] = []

    # PEP 621 style: [project] dependencies = [...]
    project_deps = data.get("project", {}).get("dependencies", [])
    if isinstance(project_deps, list):
        for dep in project_deps:
            if isinstance(dep, str):
                dependencies.append(dep)

    # PEP 621 optional dependencies: [project.optional-dependencies]
    optional_deps = data.get("project", {}).get("optional-dependencies", {})
    if isinstance(optional_deps, dict):
        for dep_list in optional_deps.values():
            if isinstance(dep_list, list):
                for dep in dep_list:
                    if isinstance(dep, str):
                        dependencies.append(dep)

    # Poetry style: [tool.poetry.dependencies]
    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    if isinstance(poetry_deps, dict):
        for name in poetry_deps.keys():
            if name.lower() == "python":
                continue
            dependencies.append(str(name))

    cleaned: list[str] = []
    for dep in dependencies:
        base = dep.split(";", 1)[0].strip()
        for separator in ("==", ">=", "<=", "~=", "!=", ">", "<"):
            if separator in base:
                base = base.split(separator, 1)[0].strip()
                break
        if base:
            cleaned.append(base)

    return list(dict.fromkeys(cleaned))


def _fetch_file_content(repo_url: str, path: str, timeout_seconds: int = 8) -> str:
    ref = parse_repo_url(repo_url)
    api_url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/contents/{path}"

    request = Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ai-health-inspector/0.1",
        },
    )

    def _operation() -> dict:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    payload = run_with_retry(_operation)
    encoded = payload.get("content", "")
    if not encoded:
        return ""
    return base64.b64decode(encoded).decode("utf-8")


def fetch_dependency_metrics(repo_url: str, timeout_seconds: int = 8) -> DependencyMetrics:
    try:
        requirements_text = _fetch_file_content(repo_url, "requirements.txt", timeout_seconds=timeout_seconds)
        requirements_deps = parse_requirements_text(requirements_text)

        pyproject_deps: list[str] = []
        try:
            pyproject_text = _fetch_file_content(repo_url, "pyproject.toml", timeout_seconds=timeout_seconds)
            pyproject_deps = parse_pyproject_text(pyproject_text) if pyproject_text else []
        except HTTPError as exc:
            if exc.code != 404:
                raise

        all_deps = list(dict.fromkeys(requirements_deps + pyproject_deps))
        return DependencyMetrics(total_dependencies=len(all_deps), outdated_dependencies=0)
    except HTTPError as exc:
        if exc.code == 404:
            # Repo may not use either requirements.txt or pyproject.toml.
            return DependencyMetrics(total_dependencies=0, outdated_dependencies=0)
        raise DependencyParserError(f"Failed to fetch requirements.txt: {exc}") from exc
    except RetryError as exc:
        raise DependencyParserError(f"Failed to fetch requirements.txt: {exc}") from exc
    except (URLError, TimeoutError) as exc:
        raise DependencyParserError(f"Failed to fetch requirements.txt: {exc}") from exc
