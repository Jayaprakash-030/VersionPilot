import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.main import parse_args, resolve_output_path


class TestMainOutputPath(unittest.TestCase):
    def test_resolve_output_path_uses_custom_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            custom = Path(tmpdir) / "reports" / "result.json"
            path = resolve_output_path("abcd1234", str(custom))
            self.assertEqual(path, custom)
            self.assertTrue(path.parent.exists())

    def test_parse_args_supports_json_flag(self) -> None:
        argv = ["prog", "https://github.com/org/repo", "--json"]
        with patch.object(sys, "argv", argv):
            args = parse_args()
        self.assertTrue(args.json)


if __name__ == "__main__":
    unittest.main()
