from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import RepoMetrics
from .retry import RetryError, run_with_retry


class GitHubClientError(Exception):
    pass


@dataclass(frozen=True)
class RepoRef:
    owner: str
    repo: str


def parse_repo_url(repo_url: str) -> RepoRef:
    parsed = urlparse(repo_url.strip())
    if parsed.scheme not in {"http", "https"} or parsed.netloc != "github.com":
        raise GitHubClientError("Repo URL must be a GitHub URL like https://github.com/owner/repo")

    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise GitHubClientError("Repo URL must include owner and repo")

    return RepoRef(owner=parts[0], repo=parts[1])


def _days_since(iso_timestamp: str) -> int:
    # GitHub returns UTC timestamp like 2026-03-10T12:34:56Z.
    pushed_at = datetime.strptime(iso_timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = now - pushed_at
    return max(0, delta.days)


def fetch_repo_metrics(repo_url: str, timeout_seconds: int = 8) -> RepoMetrics:
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

    try:
        payload = run_with_retry(_operation)
    except RetryError as exc:
        raise GitHubClientError(f"Failed to fetch repo metadata: {exc}") from exc
    except (HTTPError, URLError, TimeoutError) as exc:
        raise GitHubClientError(f"Failed to fetch repo metadata: {exc}") from exc

    pushed_at = payload.get("pushed_at")
    if not pushed_at:
        raise GitHubClientError("GitHub response missing 'pushed_at'")

    return RepoMetrics(
        stars=int(payload.get("stargazers_count", 0)),
        forks=int(payload.get("forks_count", 0)),
        last_commit_days=_days_since(pushed_at),
        open_issues=int(payload.get("open_issues_count", 0)),
        closed_issues=0,
    )
