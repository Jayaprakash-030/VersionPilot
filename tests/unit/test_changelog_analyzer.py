import unittest

from app.analysis.changelog_analyzer import ChangelogAnalyzer


class TestChangelogAnalyzer(unittest.TestCase):
    def test_analyze_release_notes_extracts_breaking_and_deprecation_findings(self) -> None:
        notes = """
- BREAKING: Removed old authentication hook
- This method is deprecated and will be removed in next major
- Performance improvements
"""
        analyzer = ChangelogAnalyzer()
        result = analyzer.analyze_release_notes(
            package_name="example-lib",
            from_version="1.2.0",
            to_version="2.0.0",
            notes_text=notes,
        )

        self.assertEqual(result["finding_count"], 2)
        self.assertEqual(result["severity_counts"]["high"], 1)
        self.assertEqual(result["severity_counts"]["medium"], 1)
        self.assertEqual(result["analysis_method"], "regex_heuristic")
        categories = [f["category"] for f in result["findings"]]
        self.assertIn("breaking_change", categories)
        self.assertIn("deprecation", categories)

    def test_skips_section_headers_and_keeps_concrete_bullets(self) -> None:
        notes = """
## 2.7.0
### Removed
**Breaking changes vs 6.0.0:**
Incompatible changes
and there may be some incompatible changes in edge cases, especially when
- Removed support for end-of-life Python 3.9. (https://github.com/urllib3/urllib3/issues/3720)
- Removed the `HTTPResponse.getheaders()` method in favor of `HTTPResponse.headers`.
- Fixed false UTF-7 detection of SHA-1 git hashes
"""
        analyzer = ChangelogAnalyzer()
        result = analyzer.analyze_release_notes(
            package_name="urllib3",
            from_version="1.26",
            to_version="2.7.0",
            notes_text=notes,
        )

        texts = [f["text"] for f in result["findings"]]
        self.assertTrue(any("Python 3.9" in t for t in texts))
        self.assertTrue(any("getheaders" in t for t in texts))
        self.assertFalse(any(t.strip() == "### Removed" for t in texts))
        self.assertFalse(any("Incompatible changes" == t for t in texts))
        self.assertFalse(any("Breaking changes vs 6.0.0" in t for t in texts))
        self.assertFalse(any(t.startswith("and there may be") for t in texts))
        # Bugfix without removed/breaking keywords should not appear
        self.assertFalse(any("UTF-7" in t for t in texts))
        self.assertTrue(all(f["confidence"] == "regex_heuristic" for f in result["findings"]))


if __name__ == "__main__":
    unittest.main()
