from __future__ import annotations

import json
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.github_client import parse_repo_url
from app.core.retry import RetryError, run_with_retry


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


def _extract_github_repo_url(project_urls: dict[str, str] | None, home_page: str | None) -> str | None:
    candidates: list[str] = []
    if isinstance(project_urls, dict):
        candidates.extend(str(v) for v in project_urls.values() if isinstance(v, str))
    if isinstance(home_page, str) and home_page.strip():
        candidates.append(home_page.strip())

    for url in candidates:
        try:
            parsed = urlparse(url)
        except Exception:  # noqa: BLE001
            continue
        if parsed.netloc != "github.com":
            continue
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(parts) >= 2:
            return f"https://github.com/{parts[0]}/{parts[1]}"
    return None


def fetch_dependency_release_notes(package_name: str, timeout_seconds: int = 8) -> dict:
    request = Request(
        f"https://pypi.org/pypi/{package_name}/json",
        headers={
            "Accept": "application/json",
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
            return {
                "package": package_name,
                "status": "not_found",
                "source": "none",
                "latest_version": None,
                "notes_text": "",
            }
        raise ReleaseNotesFetcherError(f"Failed to fetch package metadata for {package_name}: {exc}") from exc
    except RetryError as exc:
        raise ReleaseNotesFetcherError(f"Failed to fetch package metadata for {package_name}: {exc}") from exc
    except (URLError, TimeoutError) as exc:
        raise ReleaseNotesFetcherError(f"Failed to fetch package metadata for {package_name}: {exc}") from exc

    info = payload.get("info", {}) if isinstance(payload, dict) else {}
    latest_version = info.get("version")
    project_urls = info.get("project_urls")
    home_page = info.get("home_page")

    github_repo_url = _extract_github_repo_url(project_urls, home_page)
    if github_repo_url:
        notes_text = fetch_release_notes(github_repo_url, timeout_seconds=timeout_seconds)
        if notes_text:
            return {
                "package": package_name,
                "status": "ok",
                "source": "github_latest_release",
                "latest_version": latest_version,
                "notes_text": notes_text,
                "upstream_repo_url": github_repo_url,
            }

    description = info.get("description")
    if isinstance(description, str) and description.strip():
        return {
            "package": package_name,
            "status": "ok",
            "source": "pypi_description",
            "latest_version": latest_version,
            "notes_text": description.strip()[:4000],
        }

    summary = info.get("summary")
    if isinstance(summary, str) and summary.strip():
        return {
            "package": package_name,
            "status": "ok",
            "source": "pypi_summary",
            "latest_version": latest_version,
            "notes_text": summary.strip(),
        }

    return {
        "package": package_name,
        "status": "no_notes_available",
        "source": "none",
        "latest_version": latest_version,
        "notes_text": "",
    }
