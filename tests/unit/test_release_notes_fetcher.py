from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.analysis.release_notes_fetcher import (
    ReleaseNotesFetcherError,
    fetch_dependency_release_notes,
    fetch_release_notes_span,
)


def test_fetch_release_notes_span_filters_versions_between_pin_and_target():
    releases = [
        {"tag_name": "v2.32.3", "body": "latest notes"},
        {"tag_name": "2.30.0", "body": "mid notes"},
        {"tag_name": "2.28.0", "body": "pin notes should be excluded"},
        {"tag_name": "v1.0.0", "body": "old notes"},
        {"tag_name": "not-a-version", "body": "ignored"},
    ]

    with patch(
        "app.analysis.release_notes_fetcher.run_with_retry",
        return_value=releases,
    ):
        notes = fetch_release_notes_span(
            "https://github.com/psf/requests",
            from_version="2.28.0",
            to_version="2.32.3",
        )

    assert "mid notes" in notes
    assert "latest notes" in notes
    assert "pin notes should be excluded" not in notes
    assert "old notes" not in notes


def test_fetch_dependency_release_notes_uses_span_when_pinned_behind_latest():
    project_payload = {
        "info": {
            "version": "2.32.3",
            "project_urls": {"Source": "https://github.com/psf/requests"},
            "home_page": "",
            "description": "",
            "summary": "",
        }
    }

    with patch(
        "app.analysis.release_notes_fetcher.run_with_retry",
        return_value=project_payload,
    ), patch(
        "app.analysis.release_notes_fetcher.fetch_release_notes_span",
        return_value="## 2.30.0\nbreaking change",
    ) as mock_span:
        result = fetch_dependency_release_notes("requests", version="2.28.0")

    mock_span.assert_called_once()
    assert result["status"] == "ok"
    assert result["source"] == "github_release_span"
    assert result["from_version"] == "2.28.0"
    assert result["to_version"] == "2.32.3"
    assert "breaking change" in result["notes_text"]


def test_fetch_dependency_release_notes_up_to_date_when_pin_equals_latest():
    project_payload = {
        "info": {
            "version": "2.28.0",
            "project_urls": {"Source": "https://github.com/psf/requests"},
            "description": "",
            "summary": "",
        }
    }

    with patch(
        "app.analysis.release_notes_fetcher.run_with_retry",
        return_value=project_payload,
    ), patch(
        "app.analysis.release_notes_fetcher.fetch_release_notes_span"
    ) as mock_span:
        result = fetch_dependency_release_notes("requests", version="2.28.0")

    mock_span.assert_not_called()
    assert result["status"] == "up_to_date"
    assert result["notes_text"] == ""
    assert result["source"] == "none"


def test_fetch_dependency_release_notes_unpinned_falls_back_to_latest():
    project_payload = {
        "info": {
            "version": "2.32.3",
            "project_urls": {"Source": "https://github.com/psf/requests"},
            "description": "",
            "summary": "",
        }
    }

    with patch(
        "app.analysis.release_notes_fetcher.run_with_retry",
        return_value=project_payload,
    ), patch(
        "app.analysis.release_notes_fetcher.fetch_release_notes",
        return_value="latest only",
    ) as mock_latest, patch(
        "app.analysis.release_notes_fetcher.fetch_release_notes_span"
    ) as mock_span:
        result = fetch_dependency_release_notes("requests", version=None)

    mock_span.assert_not_called()
    mock_latest.assert_called_once()
    assert result["source"] == "unpinned_latest_fallback"
    assert result["notes_text"] == "latest only"


def test_github_latest_failure_falls_back_to_pypi_description():
    project_payload = {
        "info": {
            "version": "2.32.3",
            "project_urls": {"Source": "https://github.com/psf/requests"},
            "description": "Package description with deprecations.",
            "summary": "",
        }
    }

    with patch(
        "app.analysis.release_notes_fetcher.run_with_retry",
        return_value=project_payload,
    ), patch(
        "app.analysis.release_notes_fetcher.fetch_release_notes",
        side_effect=ReleaseNotesFetcherError("rate limited"),
    ):
        result = fetch_dependency_release_notes("requests", version=None)

    assert result["status"] == "ok"
    assert result["source"] == "pypi_description"
    assert "deprecations" in result["notes_text"]
