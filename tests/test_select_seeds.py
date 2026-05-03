"""Tests for the seed-rotation helper used by the batch workflow."""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "last30days" / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import select_seeds  # noqa: E402


SAMPLE_TOPICS = """\
defaults:
  window_days: 30
pain_phrases:
  - 'A'
  - 'B'
  - 'C'
  - 'D'
vertical_pains:
  - 'V1'
  - 'V2'
disabled_section:
  enabled: false
  items:
    - 'never picked'
"""


class TestGatherSeeds(unittest.TestCase):
    def test_union_skips_defaults_and_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "topics.yml"
            path.write_text(SAMPLE_TOPICS)
            topics = select_seeds.load_topics(path)
            pool = select_seeds.gather_seeds(topics, category=None)
            self.assertEqual(["A", "B", "C", "D", "V1", "V2"], pool)

    def test_category_filter_restricts_pool(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "topics.yml"
            path.write_text(SAMPLE_TOPICS)
            topics = select_seeds.load_topics(path)
            pool = select_seeds.gather_seeds(topics, category="vertical_pains")
            self.assertEqual(["V1", "V2"], pool)


class TestSelectDeterministic(unittest.TestCase):
    def test_same_date_hour_picks_same_seeds(self):
        pool = list("ABCDEFGH")
        a = select_seeds.select(pool, count=3, date="2026-05-03", hour=12)
        b = select_seeds.select(pool, count=3, date="2026-05-03", hour=12)
        self.assertEqual(a, b)

    def test_different_hour_shifts_window(self):
        pool = list("ABCDEFGH")
        a = select_seeds.select(pool, count=3, date="2026-05-03", hour=0)
        b = select_seeds.select(pool, count=3, date="2026-05-03", hour=1)
        # Different start offsets produce a different ordered slice.
        self.assertNotEqual(a, b)

    def test_count_caps_at_requested(self):
        pool = list("ABCDEFGH")
        result = select_seeds.select(pool, count=2, date="2026-05-03", hour=0)
        self.assertEqual(2, len(result))

    def test_rotation_wraps_when_count_smaller_than_pool(self):
        pool = list("ABCD")
        result = select_seeds.select(pool, count=4, date="2026-05-03", hour=0)
        # 4 distinct items chosen from a 4-pool — rotation just reorders.
        self.assertEqual(set("ABCD"), set(result))


class TestMainEntryPoint(unittest.TestCase):
    def test_main_prints_n_seeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "topics.yml"
            path.write_text(SAMPLE_TOPICS)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = select_seeds.main([
                    "--topics", str(path),
                    "--count", "3",
                    "--date", "2026-05-03",
                    "--hour", "12",
                ])
            self.assertEqual(0, rc)
            self.assertEqual(3, len(buf.getvalue().strip().splitlines()))

    def test_main_returns_nonzero_on_empty_pool(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.yml"
            path.write_text("defaults: {}\n")
            rc = select_seeds.main(["--topics", str(path)])
            self.assertEqual(1, rc)

    def test_main_errors_on_missing_file(self):
        with self.assertRaises(SystemExit):
            select_seeds.main(["--topics", "/nonexistent/topics.yml"])


if __name__ == "__main__":
    unittest.main()
