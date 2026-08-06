from __future__ import annotations

import base64
import json
import tomllib
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .github_client import parse_repo_url
from .models import DependencyMetrics, DependencySpec
from .retry import RetryError, run_with_retry


class DependencyParserError(Exception):
    """Raised when dependency manifests cannot be fetched or parsed."""
    pass


MANIFEST_FILENAMES = frozenset({"requirements.txt", "pyproject.toml"})
MAX_MANIFEST_FILES = 20


def _extract_name_version(dep: str) -> DependencySpec | None:
    """Parse a requirement string into a DependencySpec name and version."""
    base = dep.split(";", 1)[0].strip()
    if not base:
        return None

    for separator in ("==", ">=", "<=", "~=", "!=", ">", "<"):
        if separator in base:
            name, version = base.split(separator, 1)
            name = name.strip()
            version = version.strip() or None
            if name:
                if "[" in name:
                    name = name.split("[", 1)[0].strip()
                return DependencySpec(name=name, version=version)
            return None

    if "[" in base:
        base = base.split("[", 1)[0].strip()

    return DependencySpec(name=base, version=None)


def parse_requirements_specs(requirements_text: str) -> list[DependencySpec]:
    """Parse requirements.txt text into unique DependencySpec entries."""
    specs: list[DependencySpec] = []
    seen_names: set[str] = set()

    for raw_line in requirements_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith(("-r", "--requirement", "-c", "--constraint", "-e", "--editable")):
            continue

        spec = _extract_name_version(line)
        if spec and spec.name not in seen_names:
            specs.append(spec)
            seen_names.add(spec.name)

    return specs


def parse_requirements_text(requirements_text: str) -> list[str]:
    """Parse requirements.txt text into a list of dependency names."""
    return [spec.name for spec in parse_requirements_specs(requirements_text)]


def parse_pyproject_specs(pyproject_text: str) -> list[DependencySpec]:
    """Parse pyproject.toml text into unique DependencySpec entries."""
    try:
        data = tomllib.loads(pyproject_text)
    except tomllib.TOMLDecodeError as exc:
        raise DependencyParserError("Could not parse pyproject.toml") from exc

    specs: list[DependencySpec] = []
    seen_names: set[str] = set()

    def _add_raw_dep(raw_dep: str) -> None:
        """Add a raw dependency string to the specs list if not already seen."""
        spec = _extract_name_version(raw_dep)
        if spec and spec.name not in seen_names:
            specs.append(spec)
            seen_names.add(spec.name)

    # PEP 621 style: [project] dependencies = [...]
    project_deps = data.get("project", {}).get("dependencies", [])
    if isinstance(project_deps, list):
        for dep in project_deps:
            if isinstance(dep, str):
                _add_raw_dep(dep)

    # PEP 621 optional dependencies: [project.optional-dependencies]
    optional_deps = data.get("project", {}).get("optional-dependencies", {})
    if isinstance(optional_deps, dict):
        for dep_list in optional_deps.values():
            if isinstance(dep_list, list):
                for dep in dep_list:
                    if isinstance(dep, str):
                        _add_raw_dep(dep)

    # Poetry style: [tool.poetry.dependencies]
    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    if isinstance(poetry_deps, dict):
        for name, value in poetry_deps.items():
            if name.lower() == "python":
                continue

            version: str | None = None
            if isinstance(value, str):
                version = value.strip() or None
            elif isinstance(value, dict):
                raw_version = value.get("version")
                if isinstance(raw_version, str):
                    version = raw_version.strip() or None

            if name not in seen_names:
                specs.append(DependencySpec(name=str(name), version=version))
                seen_names.add(str(name))

    return specs


def parse_pyproject_text(pyproject_text: str) -> list[str]:
    """Parse pyproject.toml text into a list of dependency names."""
    return [spec.name for spec in parse_pyproject_specs(pyproject_text)]


def _fetch_file_content(repo_url: str, path: str, timeout_seconds: int = 8) -> str:
    """Fetch and decode a file's contents from the GitHub Contents API."""
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


def _fetch_default_branch(repo_url: str, timeout_seconds: int = 8) -> str:
    """Fetch the repository's default branch name from GitHub."""
    ref = parse_repo_url(repo_url)
    api_url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}"

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
    branch = payload.get("default_branch")
    return str(branch or "main")


def _discover_dependency_manifest_paths(
    repo_url: str,
    timeout_seconds: int = 8,
) -> list[str]:
    """Discover requirements.txt and pyproject.toml paths in a GitHub repo tree."""
    ref = parse_repo_url(repo_url)
    default_branch = _fetch_default_branch(repo_url, timeout_seconds=timeout_seconds)
    api_url = (
        f"https://api.github.com/repos/{ref.owner}/{ref.repo}"
        f"/git/trees/{default_branch}?recursive=1"
    )

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
    paths: list[str] = []
    for entry in payload.get("tree", []):
        if entry.get("type") != "blob":
            continue
        path = str(entry.get("path", ""))
        if Path(path).name in MANIFEST_FILENAMES:
            paths.append(path)

    return sorted(paths)[:MAX_MANIFEST_FILES]


def _merge_dependency_specs(spec_groups: list[list[DependencySpec]]) -> list[DependencySpec]:
    """Merge dependency spec lists while keeping the first occurrence of each name."""
    merged: list[DependencySpec] = []
    seen_names: set[str] = set()
    for specs in spec_groups:
        for spec in specs:
            if spec.name not in seen_names:
                merged.append(spec)
                seen_names.add(spec.name)
    return merged


def fetch_dependencies(repo_url: str, timeout_seconds: int = 8) -> list[DependencySpec]:
    """Fetch and merge dependency specs from manifests in a GitHub repository."""
    dependency_groups: list[list[DependencySpec]] = []
    manifest_available = False
    errors: list[str] = []

    try:
        manifest_paths = _discover_dependency_manifest_paths(
            repo_url,
            timeout_seconds=timeout_seconds,
        )
    except HTTPError as exc:
        if exc.code == 404:
            manifest_paths = []
        else:
            errors.append(f"dependency manifest discovery failed: {exc}")
            manifest_paths = []
    except (RetryError, URLError, TimeoutError) as exc:
        errors.append(f"dependency manifest discovery failed: {exc}")
        manifest_paths = []

    for path in manifest_paths:
        try:
            manifest_text = _fetch_file_content(
                repo_url,
                path,
                timeout_seconds=timeout_seconds,
            )
            manifest_available = True
            if Path(path).name == "requirements.txt":
                dependency_groups.append(parse_requirements_specs(manifest_text))
            elif Path(path).name == "pyproject.toml" and manifest_text:
                dependency_groups.append(parse_pyproject_specs(manifest_text))
        except HTTPError as exc:
            if exc.code != 404:
                errors.append(f"{path} fetch failed: {exc}")
        except DependencyParserError as exc:
            errors.append(f"{path} parse failed: {exc}")
        except (RetryError, URLError, TimeoutError) as exc:
            errors.append(f"{path} fetch failed: {exc}")

    merged = _merge_dependency_specs(dependency_groups)

    # If at least one dependency source is available, use what we have.
    if manifest_available:
        return merged

    # Neither file found: valid case, repo may not declare dependencies here.
    if not errors:
        return []

    raise DependencyParserError("; ".join(errors))


def fetch_dependency_metrics(repo_url: str, timeout_seconds: int = 8) -> DependencyMetrics:
    """Fetch dependency counts for a repo with outdated count left at zero."""
    dependencies = fetch_dependencies(repo_url, timeout_seconds=timeout_seconds)
    return DependencyMetrics(total_dependencies=len(dependencies), outdated_dependencies=0)
