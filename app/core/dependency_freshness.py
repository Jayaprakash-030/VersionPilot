from __future__ import annotations

import json
from packaging.version import InvalidVersion, Version
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import DependencySpec
from .retry import RetryError, run_with_retry


class DependencyFreshnessError(Exception):
    pass


DEFAULT_OUTDATED_GAP_POLICY = frozenset({"major"})


def _to_mmp(version: str) -> tuple[int, int, int] | None:
    try:
        parsed = Version(version)
    except InvalidVersion:
        return None

    release = parsed.release
    if not release:
        return None

    padded = release + (0,) * (3 - len(release))
    return padded[0], padded[1], padded[2]


def _version_gap_level(current: str, latest: str) -> str:
    current_mmp = _to_mmp(current)
    latest_mmp = _to_mmp(latest)
    if current_mmp is None or latest_mmp is None:
        return "none"

    c_major, c_minor, c_patch = current_mmp
    l_major, l_minor, l_patch = latest_mmp

    if current_mmp >= latest_mmp:
        return "none"
    if c_major < l_major:
        return "major"
    if c_minor < l_minor:
        return "minor"
    if c_patch < l_patch:
        return "patch"
    return "none"


def _is_outdated(current: str, latest: str, include_gap_levels: set[str] | frozenset[str] | None = None) -> bool:
    policy = include_gap_levels if include_gap_levels is not None else DEFAULT_OUTDATED_GAP_POLICY
    return _version_gap_level(current, latest) in policy


def _fetch_latest_pypi_version(package_name: str, timeout_seconds: int = 8) -> str | None:
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
            return None
        raise DependencyFreshnessError(f"PyPI lookup failed for {package_name}: {exc}") from exc
    except RetryError as exc:
        raise DependencyFreshnessError(f"PyPI lookup failed for {package_name}: {exc}") from exc
    except (URLError, TimeoutError) as exc:
        raise DependencyFreshnessError(f"PyPI lookup failed for {package_name}: {exc}") from exc

    info = payload.get("info", {}) if isinstance(payload, dict) else {}
    version = info.get("version")
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def count_outdated_dependencies(
    dependencies: list[DependencySpec],
    timeout_seconds: int = 8,
    include_gap_levels: set[str] | frozenset[str] | None = None,
) -> int:
    policy = include_gap_levels if include_gap_levels is not None else DEFAULT_OUTDATED_GAP_POLICY
    outdated = 0
    for dep in dependencies:
        if not dep.version:
            continue

        try:
            latest = _fetch_latest_pypi_version(dep.name, timeout_seconds=timeout_seconds)
        except DependencyFreshnessError:
            # Skip single-package lookup failures and continue evaluating others.
            continue
        if not latest:
            continue

        if _is_outdated(dep.version, latest, include_gap_levels=policy):
            outdated += 1

    return outdated
