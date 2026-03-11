from __future__ import annotations

import base64
import json
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


def fetch_dependency_metrics(repo_url: str, timeout_seconds: int = 8) -> DependencyMetrics:
    ref = parse_repo_url(repo_url)
    api_url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/contents/requirements.txt"

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

    try:
        payload = run_with_retry(_operation)
    except HTTPError as exc:
        if exc.code == 404:
            # Repo may not use requirements.txt; treat as zero deps for this simple step.
            return DependencyMetrics(total_dependencies=0, outdated_dependencies=0)
        raise DependencyParserError(f"Failed to fetch requirements.txt: {exc}") from exc
    except RetryError as exc:
        raise DependencyParserError(f"Failed to fetch requirements.txt: {exc}") from exc
    except (URLError, TimeoutError) as exc:
        raise DependencyParserError(f"Failed to fetch requirements.txt: {exc}") from exc

    encoded = payload.get("content", "")
    if not encoded:
        return DependencyMetrics(total_dependencies=0, outdated_dependencies=0)

    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise DependencyParserError("Could not decode requirements.txt content") from exc

    dependencies = parse_requirements_text(decoded)
    return DependencyMetrics(total_dependencies=len(dependencies), outdated_dependencies=0)
