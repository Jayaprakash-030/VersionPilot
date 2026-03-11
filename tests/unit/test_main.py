import tempfile
import unittest
from pathlib import Path

from app.main import resolve_output_path


class TestMainOutputPath(unittest.TestCase):
    def test_resolve_output_path_uses_custom_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            custom = Path(tmpdir) / "reports" / "result.json"
            path = resolve_output_path("abcd1234", str(custom))
            self.assertEqual(path, custom)
            self.assertTrue(path.parent.exists())


if __name__ == "__main__":
    unittest.main()
