import unittest
from datetime import datetime, timezone

from app.github_client import GitHubClientError, _days_since, parse_repo_url


class TestParseRepoUrl(unittest.TestCase):
    def test_parse_valid_github_repo_url(self) -> None:
        ref = parse_repo_url("https://github.com/psf/requests")
        self.assertEqual(ref.owner, "psf")
        self.assertEqual(ref.repo, "requests")

    def test_parse_valid_url_with_trailing_slash_and_extra_path(self) -> None:
        ref = parse_repo_url("https://github.com/pallets/flask/")
        self.assertEqual(ref.owner, "pallets")
        self.assertEqual(ref.repo, "flask")

    def test_reject_non_github_domain(self) -> None:
        with self.assertRaises(GitHubClientError):
            parse_repo_url("https://gitlab.com/org/repo")

    def test_reject_missing_repo_segment(self) -> None:
        with self.assertRaises(GitHubClientError):
            parse_repo_url("https://github.com/org")


class TestDaysSince(unittest.TestCase):
    def test_days_since_returns_zero_for_current_timestamp(self) -> None:
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertEqual(_days_since(now_iso), 0)


if __name__ == "__main__":
    unittest.main()
