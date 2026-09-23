import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_fixture(out: Path, today: str) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scrape.py"), "--html", str(ROOT / "tests" / "fixture.html"),
         "--today", today, "--out", str(out),
         "--feed-url", "https://example.github.io/west-end-rss/feed.xml"],
        check=True, capture_output=True,
    )


def guids(path: Path) -> list[str]:
    return [g.text for g in ET.parse(path).getroot().iter("guid")]


class FeedsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        run_fixture(self.out, "2026-09-23")

    def tearDown(self):
        self.tmp.cleanup()

    def test_today_feed_has_only_today(self):
        self.assertEqual(guids(self.out / "feed.xml"), ["west-end-lunch-2026-09-23"])

    def test_week_feed_has_all_days_monday_first(self):
        self.assertEqual(guids(self.out / "week.xml"), [
            "west-end-lunch-2026-09-21", "west-end-lunch-2026-09-23",
            "west-end-lunch-2026-09-24", "west-end-lunch-2026-09-25",
        ])

    def test_week_feed_has_own_title_and_self_link(self):
        channel = ET.parse(self.out / "week.xml").getroot().find("channel")
        self.assertIn("vecka", channel.findtext("title").lower())
        link = channel.find("{http://www.w3.org/2005/Atom}link")
        self.assertEqual(link.get("href"), "https://example.github.io/west-end-rss/week.xml")

    def test_week_last_build_date_is_latest_day(self):
        channel = ET.parse(self.out / "week.xml").getroot().find("channel")
        self.assertTrue(channel.findtext("lastBuildDate").startswith("Fri, 25 Sep 2026"))


if __name__ == "__main__":
    unittest.main()
