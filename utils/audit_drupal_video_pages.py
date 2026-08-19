#!/usr/bin/env python3
"""Discover and audit video-bearing pages on the live Drupal site."""

from __future__ import annotations

import argparse
import csv
import re
import time
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup

from verify_video_pages import USER_AGENT, asset_name, extract_live_sources


VIDEO_FIELD_TABLES = (
    "node__field_page_first_video",
    "node__field_page_video_list",
    "node__field_video",
    "node__field_video_clip_name",
    "node__field_video_overview",
)


def candidate_nodes(sql_path: Path) -> dict[int, set[str]]:
    sql = sql_path.read_text(encoding="utf-8", errors="replace")
    candidates: dict[int, set[str]] = {}
    for table in VIDEO_FIELD_TABLES:
        marker = f"INSERT INTO `{table}` VALUES"
        start = sql.find(marker)
        if start == -1:
            continue
        end = sql.find("UNLOCK TABLES;", start)
        for bundle, nid in re.findall(
            r"^\('([^']*)',\d+,(\d+),", sql[start:end], re.MULTILINE
        ):
            candidates.setdefault(int(nid), set()).add(bundle)
    return candidates


def split_front_matter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    marker = text.find("\n---\n", 4)
    if marker == -1:
        return {}
    return yaml.safe_load(text[4:marker]) or {}


def hugo_nodes(content_dir: Path) -> dict[int, dict[str, str]]:
    nodes = {}
    for path in content_dir.rglob("*.md"):
        metadata = split_front_matter(path.read_text(encoding="utf-8", errors="replace"))
        if not metadata.get("drupal_nid"):
            continue
        nodes[int(metadata["drupal_nid"])] = {
            "hugo_title": str(metadata.get("title", "")),
            "hugo_url": str(metadata.get("url", "")),
            "hugo_content_path": str(path.relative_to(content_dir)),
        }
    return nodes


def inventory_by_url(inventory_path: Path) -> dict[str, dict[str, str]]:
    with inventory_path.open(encoding="utf-8", newline="") as source:
        return {row["url"]: row for row in csv.DictReader(source)}


def check_live_page(
    session: requests.Session, requested_url: str, timeout: int
) -> dict[str, object]:
    result: dict[str, object] = {
        "http_status": "",
        "live_url": "",
        "live_title": "",
        "live_sources": [],
        "error": "",
    }
    try:
        response = session.get(requested_url, timeout=timeout, allow_redirects=True)
        soup = BeautifulSoup(response.text, "html.parser")
        result.update(
            {
                "http_status": response.status_code,
                "live_url": response.url,
                "live_title": (
                    soup.title.get_text(" ", strip=True).removesuffix(
                        " | TeachingHistory.org"
                    )
                    if soup.title
                    else ""
                ),
                "live_sources": extract_live_sources(response.text),
            }
        )
    except requests.RequestException as error:
        result["error"] = str(error)
    return result


def main() -> None:
    utility_dir = Path(__file__).resolve().parent
    site_dir = utility_dir.parent / "teachinghistory-website"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sql", type=Path, default=utility_dir / "th_db.sql")
    parser.add_argument("--content", type=Path, default=site_dir / "content")
    parser.add_argument(
        "--inventory", type=Path, default=utility_dir / "video_pages.csv"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=utility_dir / "drupal_video_pages.csv",
    )
    parser.add_argument("--base-url", default="https://teachinghistory.org")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--delay", type=float, default=0.1)
    args = parser.parse_args()

    candidates = candidate_nodes(args.sql)
    local_nodes = hugo_nodes(args.content)
    inventory = inventory_by_url(args.inventory)

    # The introductory pages store player markup in ordinary Drupal page bodies,
    # not in a dedicated video field, so retain URL-only inventory candidates too.
    candidate_urls = {
        local_nodes[nid]["hugo_url"]
        for nid in candidates
        if nid in local_nodes and local_nodes[nid]["hugo_url"]
    }
    url_only = sorted(
        row["url"]
        for row in inventory.values()
        if row["url"] not in candidate_urls
    )

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    checks: list[tuple[int | None, set[str], dict[str, object]]] = []
    targets = [
        (nid, bundles, f"{args.base_url.rstrip('/')}/node/{nid}")
        for nid, bundles in sorted(candidates.items())
    ] + [
        (None, {"page"}, args.base_url.rstrip("/") + "/" + url.lstrip("/"))
        for url in url_only
    ]

    for index, (nid, bundles, requested_url) in enumerate(targets, start=1):
        check = check_live_page(session, requested_url, args.timeout)
        checks.append((nid, bundles, check))
        print(
            f"[{index:>3}/{len(targets)}] {check['http_status'] or 'ERR'} "
            f"{len(check['live_sources'])} video(s): {requested_url}",
            flush=True,
        )
        if index < len(targets):
            time.sleep(args.delay)

    rows = []
    no_live_video = 0
    for nid, bundles, check in checks:
        live_sources = list(check["live_sources"])
        if check["http_status"] != 200 or not live_sources:
            no_live_video += 1
            continue

        local = local_nodes.get(nid, {}) if nid is not None else {}
        live_path = "/" + str(check["live_url"]).split("/", 3)[-1]
        inventory_row = inventory.get(local.get("hugo_url", "")) or inventory.get(
            live_path
        )
        if not local and inventory_row:
            local = {
                "hugo_content_path": inventory_row["content_path"],
                "hugo_url": inventory_row["url"],
            }
        live_names = {asset_name(source) for source in live_sources}
        if inventory_row:
            expected_names = {
                asset_name(source)
                for source in inventory_row["video_sources"].split(" | ")
            }
            comparison = "match" if expected_names == live_names else "video mismatch"
        else:
            comparison = "missing from Hugo video inventory"

        rows.append(
            {
                "drupal_nid": nid or "",
                "drupal_content_type": " | ".join(sorted(bundles)),
                "title": check["live_title"],
                "url": live_path,
                "live_video_count": len(live_sources),
                "live_video_sources": " | ".join(live_sources),
                "in_hugo_content": str(bool(local)).lower(),
                "hugo_content_path": local.get("hugo_content_path", ""),
                "hugo_url": local.get("hugo_url", ""),
                "in_hugo_video_inventory": str(bool(inventory_row)).lower(),
                "comparison": comparison,
            }
        )

    rows.sort(key=lambda row: (row["url"], row["title"]))
    fieldnames = [
        "drupal_nid",
        "drupal_content_type",
        "title",
        "url",
        "live_video_count",
        "live_video_sources",
        "in_hugo_content",
        "hugo_content_path",
        "hugo_url",
        "in_hugo_video_inventory",
        "comparison",
    ]
    with args.output.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    missing_inventory = sum(
        row["comparison"] == "missing from Hugo video inventory" for row in rows
    )
    missing_content = sum(row["in_hugo_content"] == "false" for row in rows)
    print(
        f"Wrote {len(rows)} live video pages to {args.output}; "
        f"{missing_inventory} missing from the prior inventory, "
        f"{missing_content} absent from the final Hugo content tree, "
        f"{no_live_video} candidates had no live rendered video."
    )


if __name__ == "__main__":
    main()
