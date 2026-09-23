#!/usr/bin/env python3
"""
West End Food Court (Arendal) -> RSS 2.0

Hamtar https://west-end.se/, plockar ut veckans lunchmeny (en dag per
textblock) och skriver:
  docs/feed.xml    RSS-flodet, ett inlagg per dag
  docs/index.html  enkel mobilvanlig sida med veckans meny
  docs/menu.json   historik, sa att aldre dagar ligger kvar i flodet

Anvandning:
  python scrape.py                         # hamta live och bygg
  python scrape.py --html sida.html        # testa mot sparad HTML
  python scrape.py --today 2026-09-23      # simulera ett datum
  python scrape.py --all-week              # publicera hela veckan direkt
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, time, timedelta
from email.utils import format_datetime
from html import escape as html_escape
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://west-end.se/"
TZ = ZoneInfo("Europe/Stockholm")
USER_AGENT = "Mozilla/5.0 (compatible; west-end-lunch-rss/1.0; privat flode, 1-2 hamtningar/dag)"

WEEKDAYS = ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag"]
DAY_RE = re.compile(r"^(måndag|tisdag|onsdag|torsdag|fredag|lördag|söndag)\s+(\d{1,2})\s*/\s*(\d{1,2})", re.I)
CLOSED_RE = re.compile(r"^stängt", re.I)
VEG_RE = re.compile(r"^vegetari\w*\s+alter\w*\s*:?\s*", re.I)  # fangar aven stavfelet "alterantiv"
PRICE_RE = re.compile(r"Pris:\s*(\d+)\s*:-", re.I)

# Stationer som ar samma varje dag och inte behover synas i rubriken
TITLE_SKIP = {"SALLADSBAREN"}
KEEP_DAYS = 45  # hur manga dagar bakat flodet sparar


# ---------------------------------------------------------------- parsing

def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def is_station_heading(el, text: str) -> bool:
    """Stationsrubriker ar ibland <h3>, ibland <p><span style=bold>, ibland bara <p>VERSALER</p>."""
    if el.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return True
    if len(text) > 40 or CLOSED_RE.match(text):
        return False
    return any(c.isalpha() for c in text) and text == text.upper()


def infer_date(day: int, month: int, today: date) -> date | None:
    """Sidan anger bara dag/manad. Valj det ar som ligger narmast idag (hanterar arsskifte)."""
    candidates = []
    for y in (today.year - 1, today.year, today.year + 1):
        try:
            candidates.append(date(y, month, day))
        except ValueError:
            pass
    return min(candidates, key=lambda d: abs((d - today).days)) if candidates else None


def parse_menu(page_html: str, today: date) -> tuple[list[dict], str | None]:
    soup = BeautifulSoup(page_html, "html.parser")
    price_match = PRICE_RE.search(soup.get_text(" "))
    price = price_match.group(1) if price_match else None

    days: list[dict] = []
    for block in soup.select("div.avia_textblock"):
        current = None
        station = None
        for el in block.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p"]):
            text = clean(el.get_text(" "))
            if not text:
                continue

            m = DAY_RE.match(text)
            if m:
                d = infer_date(int(m.group(2)), int(m.group(3)), today)
                if d is None:
                    continue
                named = m.group(1).capitalize()
                if WEEKDAYS[d.weekday()].lower() != named.lower():
                    print(f"Varning: {text!r} matchar inte veckodagen for {d}", file=sys.stderr)
                current = {"date": d.isoformat(), "label": f"{WEEKDAYS[d.weekday()]} {d.day}/{d.month}", "stations": []}
                days.append(current)
                station = None
                continue

            if current is None:
                continue  # text fore forsta dagrubriken (oppettider, pris osv.)

            if is_station_heading(el, text):
                station = {"name": text, "dishes": [], "closed": False}
                current["stations"].append(station)
                continue

            if station is None:
                station = {"name": "ÖVRIGT", "dishes": [], "closed": False}
                current["stations"].append(station)

            if CLOSED_RE.match(text):
                station["closed"] = True
            else:
                station["dishes"].append(text)

    # Slå ihop om samma datum skulle förekomma två gånger
    uniq: dict[str, dict] = {}
    for day in days:
        uniq[day["date"]] = day
    return sorted(uniq.values(), key=lambda d: d["date"]), price


# ---------------------------------------------------------------- formatting

def short_name(dish: str) -> str:
    """'Pannbiff, gräddsås, ...' -> 'Pannbiff'  |  'Paneng Curry Gai/ kyckling/ ...' -> 'Paneng Curry Gai'"""
    return re.split(r"[/,]", dish, maxsplit=1)[0].strip().rstrip(".")


def pretty_station(name: str) -> str:
    return name.title().replace(" & ", " & ")


def make_title(day: dict) -> str:
    mains = []
    for st in day["stations"]:
        if st["name"].upper() in TITLE_SKIP or st["closed"]:
            continue
        for dish in st["dishes"]:
            if not VEG_RE.match(dish):
                mains.append(short_name(dish))
                break
    return f"{day['label']}: {', '.join(mains)}" if mains else day["label"]


def make_description_html(day: dict, price: str | None) -> str:
    parts = []
    for st in day["stations"]:
        parts.append(f"<h3>{html_escape(pretty_station(st['name']))}</h3>")
        if st["closed"] and not st["dishes"]:
            parts.append("<p><em>Stängt</em></p>")
            continue
        items = []
        for dish in st["dishes"]:
            if VEG_RE.match(dish):
                items.append(f"<li><strong>Vegetariskt:</strong> {html_escape(VEG_RE.sub('', dish))}</li>")
            else:
                items.append(f"<li>{html_escape(dish)}</li>")
        parts.append("<ul>" + "".join(items) + "</ul>")
    footer = "Lunch 11.00–13.00"
    if price:
        footer += f", {price} kr (bröd, salladsskål och kaffe/te ingår)"
    parts.append(f"<p><small>{html_escape(footer)}</small></p>")
    return "".join(parts)


def pub_datetime(iso: str) -> datetime:
    return datetime.combine(date.fromisoformat(iso), time(7, 0), TZ)


def build_rss(items: list[dict], feed_url: str | None) -> str:
    last = format_datetime(pub_datetime(items[0]["date"])) if items else format_datetime(datetime.now(TZ))
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        "<title>West End Food Court – Lunch</title>",
        f"<link>{SOURCE_URL}</link>",
        "<description>Dagens lunch på West End Food Court, Arendal (inofficiellt flöde)</description>",
        "<language>sv-se</language>",
        f"<lastBuildDate>{last}</lastBuildDate>",
        "<ttl>180</ttl>",
    ]
    if feed_url:
        out.append(f'<atom:link href="{xml_escape(feed_url)}" rel="self" type="application/rss+xml"/>')
    for it in items:
        out += [
            "<item>",
            f"<title>{xml_escape(it['title'])}</title>",
            f"<link>{SOURCE_URL}</link>",
            f'<guid isPermaLink="false">west-end-lunch-{it["date"]}</guid>',
            f"<pubDate>{format_datetime(pub_datetime(it['date']))}</pubDate>",
            f"<description>{xml_escape(it['html'])}</description>",
            "</item>",
        ]
    out += ["</channel>", "</rss>", ""]
    return "\n".join(out)


def build_index(week: list[dict], today: date, feed_url: str | None) -> str:
    cards = []
    for it in week:
        is_today = it["date"] == today.isoformat()
        cards.append(
            f'<section class="day{" today" if is_today else ""}" id="d{it["date"]}">'
            f'<h2>{html_escape(it["label"])}{" · idag" if is_today else ""}</h2>{it["html"]}</section>'
        )
    feed_link = feed_url or "feed.xml"
    return f"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>West End – Lunch</title>
<link rel="alternate" type="application/rss+xml" title="West End Lunch" href="{html_escape(feed_link)}">
<style>
:root{{--bg:#f6f5f2;--card:#fff;--fg:#1d1d1b;--muted:#6b6b66;--accent:#b5462b}}
@media (prefers-color-scheme:dark){{:root{{--bg:#161615;--card:#22221f;--fg:#ecebe6;--muted:#a3a29b;--accent:#e2805f}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}}
main{{max-width:720px;margin:0 auto;padding:16px}}
header p{{color:var(--muted);margin-top:0}}
a{{color:var(--accent)}}
.day{{background:var(--card);border-radius:12px;padding:12px 16px;margin:12px 0}}
.day.today{{outline:2px solid var(--accent)}}
.day h2{{margin:.2em 0 .4em;font-size:1.2rem}}
.day h3{{margin:.8em 0 .2em;font-size:.8rem;letter-spacing:.06em;text-transform:uppercase;color:var(--accent)}}
.day ul{{margin:0;padding-left:1.1em}} small{{color:var(--muted)}}
</style></head><body><main>
<header><h1>West End – Lunch</h1>
<p>Inofficiell kopia av <a href="{SOURCE_URL}">west-end.se</a>. <a href="{html_escape(feed_link)}">RSS-flöde</a></p></header>
{''.join(cards) or '<p>Ingen meny hittades.</p>'}
</main></body></html>
"""


# ---------------------------------------------------------------- main

def fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    r.encoding = r.encoding or "utf-8"
    return r.text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", help="las HTML fran fil i stallet for att hamta sidan")
    ap.add_argument("--out", default="docs", help="utmapp (default: docs)")
    ap.add_argument("--today", help="YYYY-MM-DD, for test")
    ap.add_argument("--feed-url", help="publik URL till feed.xml (for atom:self-lanken)")
    ap.add_argument("--all-week", action="store_true", help="publicera aven kommande dagar")
    args = ap.parse_args()

    today = date.fromisoformat(args.today) if args.today else datetime.now(TZ).date()
    page = Path(args.html).read_text(encoding="utf-8") if args.html else fetch(SOURCE_URL)

    days, price = parse_menu(page, today)
    if not days:
        print("FEL: hittade inga dagar på sidan. Har layouten ändrats? Flödet lämnas orört.", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    store_path = out / "menu.json"
    store: dict[str, dict] = json.loads(store_path.read_text(encoding="utf-8")) if store_path.exists() else {}

    week = []
    for day in days:
        item = {"date": day["date"], "label": day["label"], "title": make_title(day),
                "html": make_description_html(day, price)}
        store[day["date"]] = item
        week.append(item)

    cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
    store = {k: v for k, v in store.items() if k >= cutoff}

    visible = [v for k, v in store.items() if args.all_week or k <= today.isoformat()]
    visible.sort(key=lambda v: v["date"], reverse=True)
    if not args.all_week:
        visible = visible[:1]  # bara dagens meny (eller senaste dagen om dagens inte finns an)

    store_path.write_text(json.dumps(dict(sorted(store.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / "feed.xml").write_text(build_rss(visible, args.feed_url), encoding="utf-8")
    (out / "index.html").write_text(build_index(week, today, args.feed_url), encoding="utf-8")

    print(f"OK: {len(days)} dagar på sidan, {len(visible)} inlägg i flödet ({out}/feed.xml)")
    for it in week:
        print("  ", it["title"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
