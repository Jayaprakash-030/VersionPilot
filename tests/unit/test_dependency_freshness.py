import unittest

from app.dependency_freshness import _is_outdated, _version_gap_level


class TestDependencyFreshness(unittest.TestCase):
    def test_version_gap_level_classifies_major_minor_patch(self) -> None:
        self.assertEqual(_version_gap_level("1.9.0", "2.0.0"), "major")
        self.assertEqual(_version_gap_level("2.30.0", "2.31.0"), "minor")
        self.assertEqual(_version_gap_level("2.30.1", "2.30.5"), "patch")
        self.assertEqual(_version_gap_level("2.31.0", "2.31.0"), "none")

    def test_is_outdated_counts_only_major_gaps(self) -> None:
        self.assertTrue(_is_outdated("1.9.0", "2.0.0"))
        self.assertFalse(_is_outdated("2.30.0", "2.31.0"))
        self.assertFalse(_is_outdated("2.30.1", "2.30.5"))
        self.assertFalse(_is_outdated("2.31.0", "2.31.0"))
        self.assertFalse(_is_outdated("2.32.0", "2.31.0"))

    def test_version_gap_handles_prerelease_strings(self) -> None:
        # PEP 440: rc is lower than final.
        self.assertEqual(_version_gap_level("1.0rc1", "1.0"), "none")


if __name__ == "__main__":
    unittest.main()
