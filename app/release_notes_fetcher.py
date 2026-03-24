from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .github_client import parse_repo_url
from .retry import RetryError, run_with_retry


class ReleaseNotesFetcherError(Exception):
    pass


def fetch_release_notes(repo_url: str, timeout_seconds: int = 8) -> str | None:
    ref = parse_repo_url(repo_url)
    release_url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/releases/latest"
    request = Request(
        release_url,
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
            return None
        raise ReleaseNotesFetcherError(f"Failed to fetch release notes: {exc}") from exc
    except RetryError as exc:
        raise ReleaseNotesFetcherError(f"Failed to fetch release notes: {exc}") from exc
    except (URLError, TimeoutError) as exc:
        raise ReleaseNotesFetcherError(f"Failed to fetch release notes: {exc}") from exc

    body = payload.get("body") if isinstance(payload, dict) else None
    if isinstance(body, str) and body.strip():
        return body
    return None
