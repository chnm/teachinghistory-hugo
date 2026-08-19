#!/usr/bin/env python3
"""Compare the Hugo video-page inventory with the live Drupal site."""

from __future__ import annotations

import argparse
import csv
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup


VIDEO_RE = re.compile(
    r"""(?P<src>
        (?:https?://|/)
        [^"'<>\s]+?
        \.(?:mp4|m4v|mov|webm|ogv)
        (?![a-z0-9])
        (?:[?#][^"'<>\s]*)?
    )""",
    re.IGNORECASE | re.VERBOSE,
)
USER_AGENT = "TeachingHistory-Hugo-Video-Audit/1.0 (site migration verification)"


def clean_source(source: str) -> str:
    return unquote(source.replace("&amp;", "&")).rstrip(".,;")


def asset_name(source: str) -> str:
    return Path(urlparse(source).path).name


def extract_live_sources(html: str) -> list[str]:
    return list(
        dict.fromkeys(clean_source(match.group("src")) for match in VIDEO_RE.finditer(html))
    )


def check_page(
    session: requests.Session, base_url: str, row: dict[str, str], timeout: int
) -> dict[str, str | int]:
    requested_url = base_url.rstrip("/") + "/" + row["url"].lstrip("/")
    result: dict[str, str | int] = {
        **row,
        "live_http_status": "",
        "live_final_url": "",
        "live_page_title": "",
        "live_video_count": "",
        "live_video_sources": "",
        "comparison": "request failed",
        "comparison_notes": "",
    }
    try:
        response = session.get(requested_url, timeout=timeout, allow_redirects=True)
        result["live_http_status"] = response.status_code
        result["live_final_url"] = response.url
        soup = BeautifulSoup(response.text, "html.parser")
        result["live_page_title"] = soup.title.get_text(" ", strip=True) if soup.title else ""

        live_sources = extract_live_sources(response.text)
        result["live_video_count"] = len(live_sources)
        result["live_video_sources"] = " | ".join(live_sources)

        expected_sources = row["video_sources"].split(" | ")
        expected_names = {asset_name(source) for source in expected_sources}
        live_names = {asset_name(source) for source in live_sources}
        missing = sorted(expected_names - live_names)
        extra = sorted(live_names - expected_names)

        page_not_found = "page not found" in str(result["live_page_title"]).lower()
        if response.status_code != 200 or page_not_found:
            result["comparison"] = "live page unavailable"
        elif expected_names == live_names:
            result["comparison"] = "match"
        elif not live_names:
            result["comparison"] = "no video found on live page"
        else:
            result["comparison"] = "video mismatch"

        notes = []
        if missing:
            notes.append("missing live: " + ", ".join(missing))
        if extra:
            notes.append("live only: " + ", ".join(extra))
        result["comparison_notes"] = "; ".join(notes)
    except requests.RequestException as error:
        result["comparison_notes"] = str(error)
    return result


def main() -> None:
    utility_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory",
        type=Path,
        default=utility_dir / "video_pages.csv",
        help="CSV created by video_pages.py",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=utility_dir / "video_pages_drupal_check.csv",
        help="Comparison CSV output path",
    )
    parser.add_argument("--base-url", default="https://teachinghistory.org")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="Delay in seconds between requests",
    )
    args = parser.parse_args()

    with args.inventory.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    results = []
    for index, row in enumerate(rows, start=1):
        result = check_page(session, args.base_url, row, args.timeout)
        results.append(result)
        print(
            f"[{index:>2}/{len(rows)}] {result['comparison']}: {row['url']}",
            flush=True,
        )
        if index < len(rows):
            time.sleep(args.delay)

    fieldnames = list(rows[0]) + [
        "live_http_status",
        "live_final_url",
        "live_page_title",
        "live_video_count",
        "live_video_sources",
        "comparison",
        "comparison_notes",
    ]
    with args.output.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    counts: dict[str, int] = {}
    for result in results:
        comparison = str(result["comparison"])
        counts[comparison] = counts.get(comparison, 0) + 1
    summary = ", ".join(f"{name}: {count}" for name, count in sorted(counts.items()))
    print(f"Wrote {len(results)} checks to {args.output} ({summary}).")


if __name__ == "__main__":
    main()
