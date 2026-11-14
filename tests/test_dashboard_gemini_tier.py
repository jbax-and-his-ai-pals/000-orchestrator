import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import overview  # noqa: E402

UTC = dt.timezone.utc


def ev(ts, message):
    return {"actor": "reviewer-gemini", "ts": ts, "kind": "log", "message": message}


class GeminiFreeTierTests(unittest.TestCase):
    def test_today_429_exhausts_and_old_or_lookalike_codes_do_not(self):
        now = dt.datetime(2026, 11, 14, 3, 30, tzinfo=UTC)  # Fri 7:30 PM PST
        result = overview._gemini_free_tier([
            ev("2026-11-13T19:00:00-08:00", "gemini 429 rate limit"),
            ev("2026-11-12T20:00:00-08:00", "429 yesterday"),
            ev("2026-11-13T09:00:00-08:00", "ok 4290 tokens"),
        ], now)
        self.assertEqual(result["runs_today"], 2)
        self.assertTrue(result["exhausted"])
        self.assertEqual(result["resets_at"], "2026-11-14T08:00:00+00:00")

    def test_unused_day_and_daylight_time_reset(self):
        summer = dt.datetime(2026, 7, 1, 18, 0, tzinfo=UTC)  # PDT
        result = overview._gemini_free_tier([], summer)
        self.assertFalse(result["exhausted"])
        self.assertEqual(result["runs_today"], 0)
        self.assertEqual(result["resets_at"], "2026-07-02T07:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
