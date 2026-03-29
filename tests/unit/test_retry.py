import unittest

from app.core.retry import run_with_retry


class TestRetry(unittest.TestCase):
    def test_run_with_retry_eventually_succeeds(self) -> None:
        state = {"attempts": 0}

        def flaky() -> str:
            state["attempts"] += 1
            if state["attempts"] < 3:
                raise TimeoutError("temporary")
            return "ok"

        result = run_with_retry(flaky, max_attempts=3, base_delay_seconds=0.001)
        self.assertEqual(result, "ok")
        self.assertEqual(state["attempts"], 3)


if __name__ == "__main__":
    unittest.main()
