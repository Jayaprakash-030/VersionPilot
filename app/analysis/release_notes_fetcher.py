from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

from app.core.github_client import parse_repo_url
from app.core.retry import RetryError, run_with_retry

_NOTES_CHAR_LIMIT = 12_000


class ReleaseNotesFetcherError(Exception):
    """Raised when release notes or package metadata cannot be fetched."""

    pass


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-health-inspector/0.1",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_release_notes(repo_url: str, timeout_seconds: int = 8) -> str | None:
    """Fetch the latest GitHub release body for a repository URL."""
    ref = parse_repo_url(repo_url)
    release_url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/releases/latest"
    request = Request(release_url, headers=_github_headers())

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


def _parse_release_tag(tag: str) -> Version | None:
    cleaned = tag.strip().lstrip("vV")
    try:
        return Version(cleaned)
    except InvalidVersion:
        return None


def fetch_release_notes_span(
    repo_url: str,
    from_version: str,
    to_version: str,
    timeout_seconds: int = 8,
) -> str:
    """Concatenate GitHub release bodies for from_version < tag <= to_version."""
    ref = parse_repo_url(repo_url)
    releases_url = (
        f"https://api.github.com/repos/{ref.owner}/{ref.repo}/releases?per_page=30"
    )
    request = Request(releases_url, headers=_github_headers())

    def _operation() -> list:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        releases = run_with_retry(_operation)
    except HTTPError as exc:
        if exc.code == 404:
            return ""
        raise ReleaseNotesFetcherError(f"Failed to fetch release list: {exc}") from exc
    except RetryError as exc:
        raise ReleaseNotesFetcherError(f"Failed to fetch release list: {exc}") from exc
    except (URLError, TimeoutError) as exc:
        raise ReleaseNotesFetcherError(f"Failed to fetch release list: {exc}") from exc

    if not isinstance(releases, list):
        return ""

    try:
        lo = Version(from_version)
        hi = Version(to_version)
    except InvalidVersion:
        return ""

    chunks: list[str] = []
    for release in releases:
        if not isinstance(release, dict):
            continue
        tag = release.get("tag_name") or ""
        ver = _parse_release_tag(str(tag))
        if ver is None or not (lo < ver <= hi):
            continue
        body = release.get("body")
        if isinstance(body, str) and body.strip():
            chunks.append(f"## {tag}\n{body.strip()}")

    return "\n\n".join(chunks)[:_NOTES_CHAR_LIMIT]


def _extract_github_repo_url(
    project_urls: dict[str, str] | None, home_page: str | None
) -> str | None:
    """Extract a GitHub repo URL from PyPI project URLs or homepage."""
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


def _pypi_fallback_notes(info: dict, latest_version: str | None, package_name: str) -> dict:
    description = info.get("description")
    if isinstance(description, str) and description.strip():
        return {
            "package": package_name,
            "status": "ok",
            "source": "pypi_description",
            "from_version": None,
            "to_version": latest_version,
            "latest_version": latest_version,
            "notes_text": description.strip()[:4000],
        }

    summary = info.get("summary")
    if isinstance(summary, str) and summary.strip():
        return {
            "package": package_name,
            "status": "ok",
            "source": "pypi_summary",
            "from_version": None,
            "to_version": latest_version,
            "latest_version": latest_version,
            "notes_text": summary.strip(),
        }

    return {
        "package": package_name,
        "status": "no_notes_available",
        "source": "none",
        "from_version": None,
        "to_version": latest_version,
        "latest_version": latest_version,
        "notes_text": "",
    }


def fetch_dependency_release_notes(
    package_name: str,
    version: str | None = None,
    timeout_seconds: int = 8,
) -> dict:
    """Fetch release notes for a PyPI package from GitHub or PyPI metadata.

    When ``version`` (pin) is set and behind latest, concatenates GitHub release
    notes for tags in (pin, latest]. Falls back to latest-only notes otherwise.
    """
    # Always use project JSON so latest_version is the true latest on PyPI.
    pypi_url = f"https://pypi.org/pypi/{package_name}/json"
    request = Request(
        pypi_url,
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
                "from_version": version,
                "to_version": None,
                "latest_version": None,
                "notes_text": "",
            }
        raise ReleaseNotesFetcherError(
            f"Failed to fetch package metadata for {package_name}: {exc}"
        ) from exc
    except RetryError as exc:
        raise ReleaseNotesFetcherError(
            f"Failed to fetch package metadata for {package_name}: {exc}"
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise ReleaseNotesFetcherError(
            f"Failed to fetch package metadata for {package_name}: {exc}"
        ) from exc

    info = payload.get("info", {}) if isinstance(payload, dict) else {}
    latest_version = info.get("version") if isinstance(info.get("version"), str) else None
    project_urls = info.get("project_urls")
    home_page = info.get("home_page")
    github_repo_url = _extract_github_repo_url(project_urls, home_page)

    base = {
        "package": package_name,
        "from_version": version,
        "to_version": latest_version,
        "latest_version": latest_version,
        "upstream_repo_url": github_repo_url,
    }

    if version and latest_version:
        try:
            if Version(version) >= Version(latest_version):
                return {
                    **base,
                    "status": "up_to_date",
                    "source": "none",
                    "notes_text": "",
                }
        except InvalidVersion:
            pass

    if github_repo_url and version and latest_version:
        try:
            if Version(version) < Version(latest_version):
                span_notes = fetch_release_notes_span(
                    github_repo_url,
                    from_version=version,
                    to_version=latest_version,
                    timeout_seconds=timeout_seconds,
                )
                if span_notes.strip():
                    return {
                        **base,
                        "status": "ok",
                        "source": "github_release_span",
                        "notes_text": span_notes,
                    }
        except (InvalidVersion, ReleaseNotesFetcherError):
            pass

    if github_repo_url:
        try:
            notes_text = fetch_release_notes(
                github_repo_url, timeout_seconds=timeout_seconds
            )
        except ReleaseNotesFetcherError:
            notes_text = None
        if notes_text:
            if version:
                source = "github_latest_release_fallback"
            else:
                source = "unpinned_latest_fallback"
            return {
                **base,
                "status": "ok",
                "source": source,
                "notes_text": notes_text,
            }

    fallback = _pypi_fallback_notes(info, latest_version, package_name)
    fallback["from_version"] = version
    fallback["to_version"] = latest_version
    if github_repo_url:
        fallback["upstream_repo_url"] = github_repo_url
    return fallback
