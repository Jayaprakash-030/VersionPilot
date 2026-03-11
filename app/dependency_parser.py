from __future__ import annotations

import base64
import json
import tomllib
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .github_client import parse_repo_url
from .models import DependencyMetrics, DependencySpec
from .retry import RetryError, run_with_retry


class DependencyParserError(Exception):
    pass


def _extract_name_version(dep: str) -> DependencySpec | None:
    base = dep.split(";", 1)[0].strip()
    if not base:
        return None

    for separator in ("==", ">=", "<=", "~=", "!=", ">", "<"):
        if separator in base:
            name, version = base.split(separator, 1)
            name = name.strip()
            version = version.strip() or None
            if name:
                return DependencySpec(name=name, version=version)
            return None

    return DependencySpec(name=base, version=None)


def parse_requirements_specs(requirements_text: str) -> list[DependencySpec]:
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
    return [spec.name for spec in parse_requirements_specs(requirements_text)]


def parse_pyproject_specs(pyproject_text: str) -> list[DependencySpec]:
    try:
        data = tomllib.loads(pyproject_text)
    except tomllib.TOMLDecodeError as exc:
        raise DependencyParserError("Could not parse pyproject.toml") from exc

    specs: list[DependencySpec] = []
    seen_names: set[str] = set()

    def _add_raw_dep(raw_dep: str) -> None:
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
    return [spec.name for spec in parse_pyproject_specs(pyproject_text)]


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


def fetch_dependencies(repo_url: str, timeout_seconds: int = 8) -> list[DependencySpec]:
    requirements_deps: list[DependencySpec] = []
    pyproject_deps: list[DependencySpec] = []
    requirements_available = False
    pyproject_available = False
    errors: list[str] = []

    try:
        requirements_text = _fetch_file_content(repo_url, "requirements.txt", timeout_seconds=timeout_seconds)
        requirements_deps = parse_requirements_specs(requirements_text)
        requirements_available = True
    except HTTPError as exc:
        if exc.code != 404:
            errors.append(f"requirements.txt fetch failed: {exc}")
    except (RetryError, URLError, TimeoutError) as exc:
        errors.append(f"requirements.txt fetch failed: {exc}")

    try:
        pyproject_text = _fetch_file_content(repo_url, "pyproject.toml", timeout_seconds=timeout_seconds)
        pyproject_available = True
        if pyproject_text:
            pyproject_deps = parse_pyproject_specs(pyproject_text)
    except HTTPError as exc:
        if exc.code != 404:
            errors.append(f"pyproject.toml fetch failed: {exc}")
    except DependencyParserError as exc:
        errors.append(f"pyproject.toml parse failed: {exc}")
    except (RetryError, URLError, TimeoutError) as exc:
        errors.append(f"pyproject.toml fetch failed: {exc}")

    merged: list[DependencySpec] = []
    seen_names: set[str] = set()
    for spec in requirements_deps + pyproject_deps:
        if spec.name not in seen_names:
            merged.append(spec)
            seen_names.add(spec.name)

    # If at least one dependency source is available, use what we have.
    if requirements_available or pyproject_available:
        return merged

    # Neither file found: valid case, repo may not declare dependencies here.
    if not errors:
        return []

    raise DependencyParserError("; ".join(errors))


def fetch_dependency_metrics(repo_url: str, timeout_seconds: int = 8) -> DependencyMetrics:
    dependencies = fetch_dependencies(repo_url, timeout_seconds=timeout_seconds)
    return DependencyMetrics(total_dependencies=len(dependencies), outdated_dependencies=0)
