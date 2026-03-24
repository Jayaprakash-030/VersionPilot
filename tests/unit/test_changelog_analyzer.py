import unittest

from app.changelog_analyzer import ChangelogAnalyzer


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
        categories = [f["category"] for f in result["findings"]]
        self.assertIn("breaking_change", categories)
        self.assertIn("deprecation", categories)


if __name__ == "__main__":
    unittest.main()
