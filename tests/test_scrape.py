import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock
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


class RetryTest(unittest.TestCase):
    """west-end.se skickar ibland en sida utan meny till GitHubs servrar."""

    def setUp(self):
        sys.path.insert(0, str(ROOT))
        import scrape
        self.scrape = scrape
        self.page = (ROOT / "tests" / "fixture.html").read_text(encoding="utf-8")
        self.today = __import__("datetime").date(2026, 9, 23)

    def test_retries_when_page_has_no_menu(self):
        with mock.patch.object(self.scrape, "fetch", side_effect=["<html></html>", self.page]), \
                mock.patch.object(self.scrape.timer, "sleep") as sleep:
            days, price = self.scrape.fetch_menu(self.today, attempts=3, delay=30)
        self.assertEqual(len(days), 4)
        sleep.assert_called_once_with(30)

    def test_retries_on_network_error(self):
        err = self.scrape.requests.ConnectionError("nere")
        with mock.patch.object(self.scrape, "fetch", side_effect=[err, self.page]), \
                mock.patch.object(self.scrape.timer, "sleep"):
            days, _ = self.scrape.fetch_menu(self.today, attempts=3, delay=30)
        self.assertEqual(len(days), 4)

    def test_gives_up_after_all_attempts(self):
        with mock.patch.object(self.scrape, "fetch", return_value="<html></html>") as fetch, \
                mock.patch.object(self.scrape.timer, "sleep"):
            days, _ = self.scrape.fetch_menu(self.today, attempts=3, delay=30)
        self.assertEqual(days, [])
        self.assertEqual(fetch.call_count, 3)


if __name__ == "__main__":
    unittest.main()
