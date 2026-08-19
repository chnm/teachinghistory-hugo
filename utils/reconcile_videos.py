#!/usr/bin/env python3
"""Reconcile live Drupal, Hugo, and YouTube video inventories.

The live Drupal site exposes serialized node fields at ``?_format=json`` even
though JSON:API is not enabled. This script uses those ordered field arrays as
the primary source of truth and retains the prior rendered-page inventory as a
fallback for URL-only pages and failed API requests.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen


TARGET_SQL_TABLES = {
    "node__field_page_first_video",
    "node__field_video",
    "node__field_video_clip_name",
}
ROW_PREFIX_RE = re.compile(
    r"^\('(?:\\'|[^'])*',\d+,(?P<nid>\d+),\d+,'(?:\\'|[^'])*',(?P<delta>\d+),"
)
VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".webm", ".ogv"}
USER_AGENT = "TeachingHistory-Hugo-Video-Reconciliation/1.0"
SERVER_INVENTORY_COMMENT_API = (
    "https://api.github.com/repos/chnm/teachinghistory-hugo/issues/comments/5122389150"
)

SARAH_BAGLEY_OVERRIDES = {
    "7FYsDgUGF2g": {
        "drupal_nid": "25692",
        "page_url": "/best-practices/examples-of-historical-thinking/25692",
        "clip_index": "1",
        "clip_title": "What interests you in these documents?",
        "asset_name": "Murphy1",
    },
    "4z7O30EkPAg": {
        "drupal_nid": "25692",
        "page_url": "/best-practices/examples-of-historical-thinking/25692",
        "clip_index": "2",
        "clip_title": "How do you analyze letters from the past?",
        "asset_name": "Murphy2",
    },
    "uxBOCBTBu1c": {
        "drupal_nid": "25692",
        "page_url": "/best-practices/examples-of-historical-thinking/25692",
        "clip_index": "3",
        "clip_title": "What advice would you give to a student reading these?",
        "asset_name": "Murphy3",
    },
}


def mapped_video(
    drupal_nid: str,
    page_url: str,
    clip_index: int,
    asset: str,
    reason: str,
) -> dict[str, str]:
    return {
        "resolution": "map",
        "drupal_nid": drupal_nid,
        "page_url": page_url,
        "clip_index": str(clip_index),
        "asset_name": asset,
        "reason": reason,
    }


MANUAL_YOUTUBE_OVERRIDES = {
    **{
        youtube_id: {
            **values,
            "resolution": "map",
            "reason": "Sarah Bagley URL correction supplied by the review team",
        }
        for youtube_id, values in SARAH_BAGLEY_OVERRIDES.items()
    },
    "UrxybbSxVDU": mapped_video("23459", "/best-practices/examples-of-historical-thinking/23459", 2, "Richard2", "Title identifies Olmsted's account"),
    "65_-sS8iUnI": mapped_video("24175", "/best-practices/examples-of-historical-thinking/24175", 3, "Allida3", "Title identifies the New Deal clip"),
    "KU5dXmBsi8g": mapped_video("24551", "/best-practices/examples-of-historical-thinking/24551", 1, "Reis1", "Title identifies Dynamics of a Confession"),
    "SRwKx5L6DBA": mapped_video("23894", "/best-practices/teaching-in-action/23894", 2, "TIA_Stacy2", "Title identifies the continuation clip"),
    "9E_UK51h4_o": mapped_video("23894", "/best-practices/teaching-in-action/23894", 4, "TIA_Stacy4", "Title identifies classroom discussion and conclusions"),
    "ZthD31zn5NU": mapped_video("25318", "/best-practices/examples-of-historical-thinking/25318", 1, "Hahn1", "Title identifies day-to-day experience"),
    "NB3lajntutQ": mapped_video("25318", "/best-practices/examples-of-historical-thinking/25318", 2, "Hahn2", "Title identifies context of the diary"),
    "_g0p97uR5Uw": mapped_video("25379", "/best-practices/examples-of-historical-thinking/25379", 2, "Tiya2", "Title identifies the Tubman context clip"),
    "dcoi5NHlAyc": mapped_video("25524", "/best-practices/examples-of-historical-thinking/25524", 3, "Pellom3", "Title identifies the human-rights clip"),
    "hQvRSstakOA": mapped_video("25860", "/best-practices/examples-of-historical-thinking/25860", 1, "Grant1", "Title identifies An Unusual Realism"),
    "qR233hOq4Qo": mapped_video("25860", "/best-practices/examples-of-historical-thinking/25860", 2, "Grant2", "Title identifies Heroic Charge or Disaster"),
    "1tLfG3gWVp8": mapped_video("25860", "/best-practices/examples-of-historical-thinking/25860", 3, "Grant3", "Title identifies Grant's Strategy"),
    "xwUxMzjHy8I": mapped_video("25860", "/best-practices/examples-of-historical-thinking/25860", 4, "Grant4", "Title identifies Grant in the Memorial"),
    "N_PfnVtc0pU": mapped_video("25847", "/best-practices/examples-of-historical-thinking/25847", 1, "wwmem1", "Title identifies the Vietnam Memorial comparison"),
    "uQBsL59Fblc": mapped_video("25847", "/best-practices/examples-of-historical-thinking/25847", 2, "wwmem2", "Title identifies the WWII Memorial contrast"),
    "4n9KQ0FQ8cg": mapped_video("25847", "/best-practices/examples-of-historical-thinking/25847", 3, "wwmem3", "Title identifies audience and symbols"),
    "VEoCZ4DYzVE": mapped_video("25851", "/best-practices/examples-of-historical-thinking/25851", 2, "AmArt6", "Title identifies the completed-mural comparison"),
    "0eE6Yv_W6TA": mapped_video("25853", "/best-practices/examples-of-historical-thinking/25853", 1, "buildingmuseum1", "Title identifies close examination of an object"),
    "IdVTZKTmjUo": mapped_video("25853", "/best-practices/examples-of-historical-thinking/25853", 2, "buildingmuseum2", "Title identifies close examination of a building"),
    "7aHwEXlFDfM": mapped_video("25853", "/best-practices/examples-of-historical-thinking/25853", 3, "buildingmuseum3", "Title identifies drawing first impressions"),
    "yIMBwA-d9s0": mapped_video("25853", "/best-practices/examples-of-historical-thinking/25853", 4, "buildingmuseum4", "Title identifies considering intent"),
    "c7gWyACfDXc": mapped_video("23893", "/best-practices/teaching-in-action/23893", 2, "TIA_MyLai2", "Title identifies the My Lai zoom-in inquiry"),
    "MuaBuDBr5DI": mapped_video("22416", "/node/22416", 2, "LL_Allida2", "Title identifies the outside-the-classroom clip"),
    "yeSyobLcSIk": mapped_video("22914", "/node/22914", 2, "LL_Alice2", "Title identifies the professional-development structure clip"),
    "ftTP2vmmXG0": mapped_video("25848", "/best-practices/examples-of-historical-thinking/25848", 1, "MontExhibit1", "Title identifies Introducing the Exhibit"),
    "fjtqSZufliI": mapped_video("25848", "/best-practices/examples-of-historical-thinking/25848", 2, "MontExhibit2", "Title identifies Presenting the Paradox"),
    "wAQcQi5V1L4": mapped_video("25848", "/best-practices/examples-of-historical-thinking/25848", 3, "MontExhibit3", "Title identifies Framing the Lives of the Enslaved"),
    "R4sYxidx6Hg": {"resolution": "duplicate_upload", "duplicate_of": "O1CLCJISkVo", "reason": "Same title and duration as the series-prefixed upload"},
    "IBq18dDYTcU": {"resolution": "duplicate_upload", "duplicate_of": "GbYiZ0u-Yic", "reason": "Same title and duration as the series-prefixed upload"},
    "N-mZwSGHxhY": {"resolution": "duplicate_upload", "duplicate_of": "2WPugFBKz3M", "reason": "Same duration, upload date, and thumbnail as the other generic promotional upload"},
    "2WPugFBKz3M": {"resolution": "youtube_only_archive", "reason": "Generic promotional upload; thumbnail does not match the proposed Drupal clip"},
    "hpvvZezgzmU": {"resolution": "obsolete_or_deleted", "reason": "Historical Film Clips page is deleted; retain only as a YouTube archive item"},
    "iIIOuOh367E": {"resolution": "obsolete_or_deleted", "reason": "Historical Film Clips page is deleted; retain only as a YouTube archive item"},
    "9KTUxUWwoS0": {"resolution": "unassigned_review", "reason": "Site Evolution does not confidently match the deleted Historical Film Clips page"},
    "Aw89mNVw2Qg": {"resolution": "youtube_only_archive", "reason": "Powhatan page is absent from the current Hugo content"},
    "qWba_ev8HEA": {"resolution": "youtube_only_archive", "reason": "Powhatan page is absent from the current Hugo content"},
    "tPrJspZlUU4": {"resolution": "youtube_only_archive", "reason": "Powhatan page is absent from the current Hugo content"},
    "k_hxPZvGVfY": {"resolution": "youtube_only_archive", "reason": "Powhatan page is absent from the current Hugo content"},
}


def normalize_path(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    path = parsed.path if parsed.scheme or parsed.netloc else value.split("?", 1)[0]
    return "/" + path.strip("/")


def asset_name(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(unquote(value))
    return Path(parsed.path).stem.strip()


def normalize_asset(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", asset_name(value).lower())


def youtube_id_from_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.netloc.endswith("youtu.be"):
        return parsed.path.strip("/")
    return parse_qs(parsed.query).get("v", [""])[0]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def candidate_nids(sql_path: Path) -> set[int]:
    active_table = ""
    nids: set[int] = set()
    with sql_path.open(encoding="utf-8", errors="replace") as source:
        for line in source:
            if line.startswith("INSERT INTO `"):
                active_table = line.split("`", 2)[1]
                continue
            if active_table not in TARGET_SQL_TABLES:
                continue
            if line.startswith("UNLOCK TABLES;"):
                active_table = ""
                continue
            match = ROW_PREFIX_RE.match(line)
            if match:
                nids.add(int(match.group("nid")))
    return nids


def simple_front_matter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    result: dict[str, str] = {}
    for key in ("drupal_nid", "title", "url"):
        match = re.search(rf"^{key}:\s*(.+?)\s*$", text[4:end], re.MULTILINE)
        if match:
            result[key] = match.group(1).strip().strip("'\"")
    return result


def hugo_pages(content_dir: Path) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    by_url: dict[str, dict[str, str]] = {}
    by_nid: dict[str, dict[str, str]] = {}
    for path in content_dir.rglob("*.md"):
        metadata = simple_front_matter(path)
        if not metadata:
            continue
        record = {
            **metadata,
            "hugo_content_path": str(path.relative_to(content_dir)),
        }
        url = normalize_path(metadata.get("url", ""))
        if url:
            by_url[url] = record
        nid = metadata.get("drupal_nid", "")
        if nid.isdigit():
            by_nid[nid] = record
    return by_url, by_nid


def api_url(value: str, base_url: str) -> str:
    if value.isdigit():
        target = f"{base_url.rstrip('/')}/node/{value}"
    else:
        target = f"{base_url.rstrip('/')}/{value.lstrip('/')}"
    return target + ("&" if "?" in target else "?") + "_format=json"


def fetch_node(target: str, base_url: str, timeout: int, attempts: int) -> dict[str, object]:
    request_url = api_url(target, base_url)
    result: dict[str, object] = {
        "target": target,
        "requested_url": request_url,
        "http_status": "",
        "final_url": "",
        "data": None,
        "error": "",
    }
    for attempt in range(1, attempts + 1):
        try:
            request = Request(
                request_url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            with urlopen(request, timeout=timeout) as response:
                result["http_status"] = response.status
                result["final_url"] = response.geturl().split("?", 1)[0]
                body = response.read().decode("utf-8")
                result["data"] = json.loads(body)
                return result
        except HTTPError as error:
            result["http_status"] = error.code
            result["final_url"] = error.geturl().split("?", 1)[0]
            result["error"] = f"HTTP {error.code}"
            if error.code in {403, 404}:
                return result
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            result["error"] = str(error)
        if attempt < attempts:
            time.sleep(0.75 * attempt)
    return result


def fetch_server_inventory(api_url: str, timeout: int) -> tuple[list[dict[str, str]], str]:
    """Read the sysadmin's server-file inventory from its GitHub issue comment."""
    try:
        request = Request(
            api_url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
        )
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        body = str(payload.get("body", ""))
        filenames = []
        for line in body.splitlines():
            filename = line.strip()
            if Path(filename).suffix.lower() in VIDEO_EXTENSIONS:
                filenames.append(filename)
        rows = [
            {
                "server_filename": filename,
                "asset_name": asset_name(filename),
                "normalized_asset": normalize_asset(filename),
                "inventory_source": api_url,
                "production_use": "upload_source_only",
            }
            for filename in sorted(set(filenames), key=str.casefold)
        ]
        return rows, ""
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        return [], str(error)


def field_values(data: dict[str, object], field: str) -> list[str]:
    values = data.get(field) or []
    result = []
    for item in values if isinstance(values, list) else []:
        if not isinstance(item, dict):
            continue
        value = item.get("value") or item.get("uri") or item.get("url") or ""
        if value:
            result.append(str(value))
    return result


def scalar_value(data: dict[str, object], field: str, key: str = "value") -> str:
    values = data.get(field) or []
    if isinstance(values, list) and values and isinstance(values[0], dict):
        return str(values[0].get(key, ""))
    return ""


def node_video_rows(fetch: dict[str, object]) -> tuple[dict[str, object], list[dict[str, object]]]:
    data = fetch.get("data")
    if not isinstance(data, dict):
        return (
            {
                "target": fetch["target"],
                "http_status": fetch["http_status"],
                "page_url": normalize_path(str(fetch.get("final_url", ""))),
                "drupal_nid": str(fetch["target"]) if str(fetch["target"]).isdigit() else "",
                "page_title": "",
                "content_type": "",
                "first_video_count": 0,
                "clip_video_count": 0,
                "external_video_count": 0,
                "title_count": 0,
                "transcript_count": 0,
                "error": fetch.get("error", ""),
            },
            [],
        )

    nid = scalar_value(data, "nid")
    title = scalar_value(data, "title")
    content_type = scalar_value(data, "type", "target_id")
    page_url = normalize_path(str(fetch.get("final_url", "")))
    first = field_values(data, "field_page_first_video")
    clips = field_values(data, "field_video_clip_name")
    external = field_values(data, "field_video")
    titles = field_values(data, "field_video_title")
    durations = field_values(data, "field_video_duration")
    transcripts = field_values(data, "field_transcript_text")
    rows: list[dict[str, object]] = []

    for index, source in enumerate(first, start=1):
        transcript_present = False
        if len(transcripts) == len(first):
            transcript_present = bool(transcripts[index - 1])
        elif len(transcripts) == len(first) + len(clips):
            transcript_present = bool(transcripts[index - 1])
        rows.append(
            {
                "drupal_nid": nid,
                "page_title": title,
                "page_url": page_url,
                "content_type": content_type,
                "clip_index": index,
                "source_field": "field_page_first_video",
                "video_source": source,
                "asset_name": asset_name(source),
                "clip_title": title,
                "duration": "",
                "transcript_present": str(transcript_present).lower(),
                "api_status": fetch["http_status"],
            }
        )

    for index, source in enumerate(clips, start=1):
        transcript_present = False
        if len(transcripts) == len(clips):
            transcript_present = bool(transcripts[index - 1])
        elif len(transcripts) == len(first) + len(clips):
            transcript_present = bool(transcripts[len(first) + index - 1])
        rows.append(
            {
                "drupal_nid": nid,
                "page_title": title,
                "page_url": page_url,
                "content_type": content_type,
                "clip_index": index,
                "source_field": "field_video_clip_name",
                "video_source": source,
                "asset_name": asset_name(source),
                "clip_title": titles[index - 1] if index <= len(titles) else "",
                "duration": durations[index - 1] if index <= len(durations) else "",
                "transcript_present": str(transcript_present).lower(),
                "api_status": fetch["http_status"],
            }
        )

    for index, source in enumerate(external, start=1):
        rows.append(
            {
                "drupal_nid": nid,
                "page_title": title,
                "page_url": page_url,
                "content_type": content_type,
                "clip_index": index,
                "source_field": "field_video",
                "video_source": source,
                "asset_name": asset_name(source) or f"external-{index}",
                "clip_title": "",
                "duration": "",
                "transcript_present": "false",
                "api_status": fetch["http_status"],
            }
        )

    node_row = {
        "target": fetch["target"],
        "http_status": fetch["http_status"],
        "page_url": page_url,
        "drupal_nid": nid,
        "page_title": title,
        "content_type": content_type,
        "first_video_count": len(first),
        "clip_video_count": len(clips),
        "external_video_count": len(external),
        "title_count": len(titles),
        "transcript_count": len(transcripts),
        "error": fetch.get("error", ""),
    }
    return node_row, rows


def make_key(nid: str, page_url: str, asset: str) -> tuple[str, str]:
    return page_identity(nid, page_url), normalize_asset(asset)


def page_identity(nid: str, page_url: str) -> str:
    return nid if nid else normalize_path(page_url)


def main() -> None:
    utility_dir = Path(__file__).resolve().parent
    repo_dir = utility_dir.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sql", type=Path, default=utility_dir / "th_db.sql")
    parser.add_argument("--content", type=Path, default=repo_dir / "teachinghistory-website" / "content")
    parser.add_argument("--hugo-inventory", type=Path, default=utility_dir / "video_pages.csv")
    parser.add_argument("--rendered-inventory", type=Path, default=utility_dir / "drupal_video_pages.csv")
    parser.add_argument("--youtube", type=Path, default=repo_dir / "youtube_video_page_matchesNATE REVIEW.csv")
    parser.add_argument(
        "--spot-check-results",
        type=Path,
        default=utility_dir / "video_spot_check_results.csv",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="https://teachinghistory.org")
    parser.add_argument("--server-comment-api", default=SERVER_INVENTORY_COMMENT_API)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--reuse-api-output",
        action="store_true",
        help="Reuse drupal_api_nodes.csv and drupal_api_videos.csv in the output directory",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    cached_server_inventory = args.output_dir / "server_video_inventory.csv"
    print("Reading the server inventory from the sysadmin's issue comment...", flush=True)
    server_rows, server_inventory_error = fetch_server_inventory(
        args.server_comment_api, args.timeout
    )
    if not server_rows and cached_server_inventory.exists():
        server_rows = read_csv(cached_server_inventory)
        server_inventory_error = (
            f"{server_inventory_error}; reused cached server inventory"
            if server_inventory_error
            else "reused cached server inventory"
        )
    server_by_asset = {
        row["normalized_asset"]: row
        for row in server_rows
        if row.get("normalized_asset")
    }

    rendered_rows = read_csv(args.rendered_inventory)
    hugo_by_url, hugo_by_nid = hugo_pages(args.content)
    cached_nodes = args.output_dir / "drupal_api_nodes.csv"
    cached_videos = args.output_dir / "drupal_api_videos.csv"
    if args.reuse_api_output and cached_nodes.exists() and cached_videos.exists():
        print("Reusing the existing Drupal API crawl output...", flush=True)
        node_rows = read_csv(cached_nodes)
        live_rows = [
            row for row in read_csv(cached_videos)
            if row.get("source_field") != "rendered_html_fallback"
        ]
        targets = [str(row["target"]) for row in node_rows]
    else:
        print("Reading Drupal video candidate nodes from the SQL export...", flush=True)
        nids = candidate_nids(args.sql)
        url_targets = sorted({row["url"] for row in rendered_rows if not row["drupal_nid"]})
        targets = [str(nid) for nid in sorted(nids)] + url_targets
        print(f"Fetching {len(targets)} public Drupal JSON records with {args.workers} workers...", flush=True)

        fetches: list[dict[str, object]] = []
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(fetch_node, target, args.base_url, args.timeout, args.attempts): target
                for target in targets
            }
            for index, future in enumerate(as_completed(futures), start=1):
                fetches.append(future.result())
                if index % 10 == 0 or index == len(futures):
                    print(f"  fetched {index}/{len(futures)}", flush=True)

        node_rows = []
        live_rows = []
        for fetch in fetches:
            node_row, videos = node_video_rows(fetch)
            node_rows.append(node_row)
            live_rows.extend(videos)
        node_rows.sort(key=lambda row: (str(row["page_url"]), str(row["target"])))
        live_rows.sort(key=lambda row: (str(row["page_url"]), str(row["source_field"]), int(row["clip_index"])))

    # Preserve the earlier rendered-page inventory for API failures and URL-only
    # pages whose video markup is stored in ordinary body content.
    live_keys = {
        make_key(str(row["drupal_nid"]), str(row["page_url"]), str(row["asset_name"]))
        for row in live_rows
    }
    api_video_pages = {
        page_identity(str(row["drupal_nid"]), str(row["page_url"]))
        for row in live_rows
        if row.get("source_field") != "field_video"
    }
    for page in rendered_rows:
        page_metadata = hugo_by_url.get(normalize_path(page["url"]), {})
        resolved_nid = page["drupal_nid"] or page_metadata.get("drupal_nid", "")
        if page_identity(resolved_nid, page["url"]) in api_video_pages:
            continue
        sources = [source for source in page["live_video_sources"].split(" | ") if source]
        for index, source in enumerate(sources, start=1):
            key = make_key(resolved_nid, page["url"], source)
            if key in live_keys:
                continue
            live_rows.append(
                {
                    "drupal_nid": resolved_nid,
                    "page_title": page["title"],
                    "page_url": page["url"],
                    "content_type": page["drupal_content_type"],
                    "clip_index": index,
                    "source_field": "rendered_html_fallback",
                    "video_source": source,
                    "asset_name": asset_name(source),
                    "clip_title": "",
                    "duration": "",
                    "transcript_present": "",
                    "api_status": "fallback",
                }
            )
            live_keys.add(key)

    hugo_rows: list[dict[str, str]] = []
    for page in read_csv(args.hugo_inventory):
        page_url = normalize_path(page["url"])
        metadata = hugo_by_url.get(page_url, {})
        nid = metadata.get("drupal_nid", "")
        for index, source in enumerate(page["video_sources"].split(" | "), start=1):
            if not source:
                continue
            hugo_rows.append(
                {
                    "drupal_nid": nid,
                    "page_title": page["title"],
                    "page_url": page_url,
                    "hugo_content_path": page["content_path"],
                    "clip_index": str(index),
                    "video_source": source,
                    "asset_name": asset_name(source),
                    "implementation": page["implementation"],
                }
            )

    youtube_rows: list[dict[str, str]] = []
    with args.youtube.open(encoding="utf-8-sig", newline="") as source:
        raw_rows = list(csv.reader(source))
    headers = raw_rows[0][:22]
    for values in raw_rows[1:]:
        row = dict(zip(headers, values[:22]))
        youtube_id = youtube_id_from_url(row.get("youtube_url", "")) or row.get("youtube_id", "")
        row["youtube_id"] = youtube_id
        review_note = values[22].strip() if len(values) > 22 else ""
        row["review_note"] = review_note
        override = MANUAL_YOUTUBE_OVERRIDES.get(youtube_id)
        if override:
            row["override_resolution"] = override["resolution"]
            row["override_reason"] = override["reason"]
            row["duplicate_of"] = override.get("duplicate_of", "")
            if override["resolution"] == "map":
                row.update(
                    {
                        key: override[key]
                        for key in ("drupal_nid", "page_url", "clip_index", "asset_name")
                    }
                )
                if override.get("clip_title"):
                    row["clip_title"] = override["clip_title"]
                row["match_confidence"] = "manual_verified"
                row["possible_duplicate_upload"] = "FALSE"
            elif override["resolution"] != "map":
                # Keep these uploads visible in the audit without allowing a bad
                # historical assignment to contaminate a current page's counts.
                row["drupal_nid"] = ""
                row["page_url"] = ""
                row["clip_index"] = ""
                row["asset_name"] = ""
            row["manual_override"] = override["reason"]
            row["review_note"] = ""
        else:
            row["override_resolution"] = ""
            row["override_reason"] = ""
            row["duplicate_of"] = ""
            row["manual_override"] = ""
        page_metadata = hugo_by_url.get(normalize_path(row.get("page_url", "")), {})
        if not row.get("drupal_nid") and page_metadata.get("drupal_nid"):
            row["drupal_nid"] = page_metadata["drupal_nid"]
        youtube_rows.append(row)

    def page_key(row: dict[str, object]) -> str:
        return page_identity(str(row.get("drupal_nid", "")), str(row.get("page_url", "")))

    live_by_page: dict[str, list[dict[str, object]]] = defaultdict(list)
    hugo_by_page: dict[str, list[dict[str, str]]] = defaultdict(list)
    youtube_by_page: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in live_rows:
        live_by_page[page_key(row)].append(row)
    for row in hugo_rows:
        hugo_by_page[page_key(row)].append(row)
    for row in youtube_rows:
        youtube_by_page[page_key(row)].append(row)

    # Create one canonical record per live asset, then attach Hugo and YouTube
    # records by exact asset identity. When filenames changed during conversion
    # (for example Zagarri1 -> OZagarri1), align the remaining records by their
    # explicit Drupal/Hugo clip order and retain an audit note.
    items: list[dict[str, object]] = []
    all_page_keys = set(live_by_page) | set(hugo_by_page) | set(youtube_by_page)
    for current_page in all_page_keys:
        page_items: list[dict[str, object]] = []
        by_asset: dict[str, dict[str, object]] = {}
        live_page = sorted(
            live_by_page.get(current_page, []),
            key=lambda row: (
                {"field_page_first_video": 0, "field_video_clip_name": 1, "field_video": 2, "rendered_html_fallback": 3}.get(str(row.get("source_field", "")), 9),
                int(row.get("clip_index", 9999)),
            ),
        )
        for row in live_page:
            normalized = normalize_asset(str(row.get("asset_name", "")))
            if normalized and normalized in by_asset:
                by_asset[normalized]["live"].append(row)
                continue
            item: dict[str, object] = {
                "live": [row],
                "hugo": [],
                "youtube": [],
                "alignment_notes": [],
            }
            page_items.append(item)
            if normalized:
                by_asset[normalized] = item

        pending_hugo: list[dict[str, str]] = []
        for row in sorted(hugo_by_page.get(current_page, []), key=lambda value: int(value["clip_index"])):
            item = by_asset.get(normalize_asset(row.get("asset_name", "")))
            if item is not None:
                item["hugo"].append(row)
            else:
                pending_hugo.append(row)

        pending_youtube: list[dict[str, str]] = []
        for row in sorted(
            youtube_by_page.get(current_page, []),
            key=lambda value: int(value["clip_index"]) if value.get("clip_index", "").isdigit() else 9999,
        ):
            item = by_asset.get(normalize_asset(row.get("asset_name", "")))
            if item is not None:
                item["youtube"].append(row)
            else:
                pending_youtube.append(row)

        def align_by_clip_index(
            pending: list[dict[str, str]], destination: str, label: str
        ) -> list[dict[str, str]]:
            remaining: list[dict[str, str]] = []
            for row in pending:
                index = row.get("clip_index", "")
                candidates = [
                    item
                    for item in page_items
                    if not item[destination]
                    and item["live"]
                    and str(item["live"][0].get("clip_index", "")) == index
                    and str(item["live"][0].get("source_field", "")) != "field_video"
                ]
                if index and len(candidates) == 1:
                    candidates[0][destination].append(row)
                    candidates[0]["alignment_notes"].append(f"{label} asset aligned by clip index")
                else:
                    remaining.append(row)
            return remaining

        pending_hugo = align_by_clip_index(pending_hugo, "hugo", "Hugo")
        pending_youtube = align_by_clip_index(pending_youtube, "youtube", "YouTube")

        for destination, pending in (("hugo", pending_hugo), ("youtube", pending_youtube)):
            for row in pending:
                page_items.append(
                    {
                        "live": [],
                        "hugo": [row] if destination == "hugo" else [],
                        "youtube": [row] if destination == "youtube" else [],
                        "alignment_notes": [],
                    }
                )
        items.extend(page_items)

    reconciliation: list[dict[str, object]] = []
    for item in items:
        live = item["live"]
        hugo = item["hugo"]
        youtube = item["youtube"]
        exemplar = (live or hugo or youtube)[0]
        live_present = bool(live)
        hugo_present = bool(hugo)
        youtube_present = bool(youtube)
        external = any(str(row.get("source_field", "")) == "field_video" for row in live)
        deleted = any("deleted" in row.get("review_note", "").lower() for row in youtube)
        override_resolutions = {
            row.get("override_resolution", "") for row in youtube
            if row.get("override_resolution")
        }
        reasons: list[str] = []

        if len(override_resolutions) == 1 and not live_present and not hugo_present:
            disposition = next(iter(override_resolutions))
        elif deleted and not live_present and not hugo_present:
            disposition = "obsolete_or_deleted"
        elif external:
            disposition = "external_video_review"
        elif live_present and not hugo_present and not youtube_present:
            disposition = "restore_to_hugo_and_upload"
        elif live_present and not hugo_present:
            disposition = "restore_to_hugo"
        elif (live_present or hugo_present) and not youtube_present:
            disposition = "upload_to_youtube"
        elif live_present and hugo_present and youtube_present:
            disposition = "matched"
        elif hugo_present and youtube_present and not live_present:
            disposition = "not_live_review"
        elif youtube_present and not live_present and not hugo_present:
            disposition = "youtube_only_review"
        else:
            disposition = "review"

        if len(youtube) > 1:
            reasons.append(f"{len(youtube)} YouTube uploads assigned to one clip")
        if (
            not override_resolutions or "unassigned_review" in override_resolutions
        ) and any(
            row.get("match_confidence") not in {"high", "manual_verified"}
            for row in youtube
        ):
            reasons.append("non-high YouTube match confidence")
        live_first = live[0] if live else {}
        hugo_first = hugo[0] if hugo else {}
        youtube_first = youtube[0] if youtube else {}
        record_asset = str(
            live_first.get("asset_name", "")
            or hugo_first.get("asset_name", "")
            or youtube_first.get("asset_name", "")
        )
        server_match = server_by_asset.get(normalize_asset(record_asset), {})
        server_source_available = bool(server_match)
        if (
            any(str(row.get("source_field", "")) == "rendered_html_fallback" for row in live)
            and not youtube_present
            and not server_source_available
        ):
            reasons.append("rendered fallback clip has no matching server upload source")
        if any(row.get("review_note") for row in youtube):
            reasons.extend(row["review_note"] for row in youtube if row.get("review_note"))

        needs_manual_review = bool(reasons) or disposition in {
            "external_video_review", "not_live_review", "youtube_only_review", "unassigned_review", "review"
        }

        page_nid = str(exemplar.get("drupal_nid", ""))
        page_url = str(exemplar.get("page_url", ""))
        page_meta = hugo_by_nid.get(page_nid, {}) if page_nid else hugo_by_url.get(normalize_path(page_url), {})
        page_title = str(exemplar.get("page_title", ""))
        clip_index = str(live_first.get("clip_index", "") or hugo_first.get("clip_index", "") or youtube_first.get("clip_index", ""))
        clip_title = str(live_first.get("clip_title", "") or youtube_first.get("clip_title", ""))
        suggested_title = page_title
        if clip_index:
            suggested_title += f" — Part {clip_index}"
        if clip_title and clip_title != page_title:
            suggested_title += f": {clip_title}"
        reconciliation.append(
            {
                "disposition": disposition,
                "needs_manual_review": str(needs_manual_review).lower(),
                "review_reason": " | ".join(dict.fromkeys(reasons)),
                "resolution_note": " | ".join(
                    dict.fromkeys(
                        [
                            *(str(note) for note in item["alignment_notes"]),
                            *(row.get("override_reason", "") for row in youtube if row.get("override_reason")),
                            *(
                                [f"{len(live)} Drupal field records normalized to one asset"]
                                if len(live) > 1 else []
                            ),
                        ]
                    )
                ),
                "drupal_nid": page_nid,
                "page_title": page_title,
                "canonical_page_url": page_url,
                "teachinghistory_url": f"{args.base_url.rstrip('/')}/{page_url.lstrip('/')}" if page_url else "",
                "hugo_content_path": str(hugo_first.get("hugo_content_path", "") or page_meta.get("hugo_content_path", "")),
                "clip_index": clip_index,
                "clip_title": clip_title,
                "asset_name": record_asset,
                "live_present": str(live_present).lower(),
                "live_source_field": " | ".join(sorted({str(row.get("source_field", "")) for row in live})),
                "live_video_source": " | ".join(str(row.get("video_source", "")) for row in live),
                "hugo_present": str(hugo_present).lower(),
                "hugo_video_source": " | ".join(row.get("video_source", "") for row in hugo),
                "youtube_present": str(youtube_present).lower(),
                "youtube_count": len(youtube),
                "youtube_ids": " | ".join(row.get("youtube_id", "") for row in youtube),
                "youtube_urls": " | ".join(row.get("youtube_url", "") for row in youtube),
                "youtube_titles": " | ".join(row.get("youtube_title", "") for row in youtube),
                "match_confidence": " | ".join(row.get("match_confidence", "") for row in youtube),
                "duplicate_of": " | ".join(row.get("duplicate_of", "") for row in youtube if row.get("duplicate_of")),
                "server_source_available": str(server_source_available).lower(),
                "server_filename": str(server_match.get("server_filename", "")),
                "migration_source_status": (
                    "already_on_youtube"
                    if youtube_present
                    else "server_file_available_for_youtube_upload"
                    if server_source_available
                    else "source_not_located"
                ),
                "transcript_present_live": str(live_first.get("transcript_present", "")),
                "live_duration": str(live_first.get("duration", "")),
                "manual_override": " | ".join(row.get("manual_override", "") for row in youtube if row.get("manual_override")),
                "suggested_youtube_title": suggested_title,
                "upload_status": (
                    "Ready: source on server"
                    if disposition in {"upload_to_youtube", "restore_to_hugo_and_upload"} and server_source_available
                    else "Blocked: source not located"
                    if disposition in {"upload_to_youtube", "restore_to_hugo_and_upload"}
                    else ""
                ),
                "final_youtube_id": "",
                "final_youtube_url": "",
            }
        )

    reconciliation.sort(
        key=lambda row: (
            str(row["disposition"]),
            str(row["canonical_page_url"]),
            int(row["clip_index"]) if str(row["clip_index"]).isdigit() else 9999,
            str(row["asset_name"]),
        )
    )

    node_fields = [
        "target", "http_status", "page_url", "drupal_nid", "page_title", "content_type",
        "first_video_count", "clip_video_count", "external_video_count", "title_count",
        "transcript_count", "error",
    ]
    live_fields = [
        "drupal_nid", "page_title", "page_url", "content_type", "clip_index",
        "source_field", "video_source", "asset_name", "clip_title", "duration",
        "transcript_present", "api_status",
    ]
    reconciliation_fields = [
        "disposition", "needs_manual_review", "review_reason", "resolution_note", "drupal_nid", "page_title", "canonical_page_url", "teachinghistory_url",
        "hugo_content_path", "clip_index", "clip_title", "asset_name", "live_present",
        "live_source_field", "live_video_source", "hugo_present", "hugo_video_source",
        "youtube_present", "youtube_count", "youtube_ids", "youtube_urls", "youtube_titles",
        "match_confidence", "duplicate_of", "server_source_available", "server_filename",
        "migration_source_status", "transcript_present_live", "live_duration", "manual_override",
        "suggested_youtube_title", "upload_status", "final_youtube_id", "final_youtube_url",
    ]
    server_fields = [
        "server_filename", "asset_name", "normalized_asset", "inventory_source", "production_use"
    ]
    write_csv(cached_server_inventory, server_rows, server_fields)
    write_csv(args.output_dir / "drupal_api_nodes.csv", node_rows, node_fields)
    write_csv(args.output_dir / "drupal_api_videos.csv", live_rows, live_fields)
    write_csv(args.output_dir / "video_reconciliation.csv", reconciliation, reconciliation_fields)

    uploads = [row for row in reconciliation if row["disposition"] == "upload_to_youtube"]
    restores = [row for row in reconciliation if row["disposition"] in {"restore_to_hugo", "restore_to_hugo_and_upload"}]
    restore_then_upload = [
        row for row in reconciliation if row["disposition"] == "restore_to_hugo_and_upload"
    ]
    reviews = [
        row for row in reconciliation
        if row["needs_manual_review"] == "true"
    ]
    resolved_exceptions = [
        row for row in reconciliation
        if row["disposition"] in {
            "duplicate_upload", "obsolete_or_deleted", "youtube_only_archive"
        } or row["manual_override"]
    ]
    write_csv(args.output_dir / "video_upload_queue.csv", uploads, reconciliation_fields)
    write_csv(args.output_dir / "video_restore_queue.csv", restores, reconciliation_fields)
    write_csv(
        args.output_dir / "video_restore_then_upload_queue.csv",
        restore_then_upload,
        reconciliation_fields,
    )
    write_csv(args.output_dir / "video_review_queue.csv", reviews, reconciliation_fields)
    write_csv(
        args.output_dir / "video_resolved_exceptions.csv",
        resolved_exceptions,
        reconciliation_fields,
    )

    page_groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in reconciliation:
        if row["drupal_nid"] or row["canonical_page_url"]:
            page_groups[(str(row["drupal_nid"]), str(row["canonical_page_url"]))].append(row)
    page_rows: list[dict[str, object]] = []
    for page_records in page_groups.values():
        first = page_records[0]
        live_count = sum(row["live_present"] == "true" for row in page_records)
        hugo_count = sum(row["hugo_present"] == "true" for row in page_records)
        youtube_count = sum(int(row["youtube_count"]) for row in page_records)
        manual_count = sum(row["needs_manual_review"] == "true" for row in page_records)
        exact = live_count == hugo_count == youtube_count and manual_count == 0
        page_rows.append(
            {
                "page_status": "exact_three_way_match" if exact else "needs_reconciliation",
                "drupal_nid": first["drupal_nid"],
                "page_title": first["page_title"],
                "canonical_page_url": first["canonical_page_url"],
                "teachinghistory_url": first["teachinghistory_url"],
                "hugo_content_path": first["hugo_content_path"],
                "live_clip_count": live_count,
                "hugo_clip_count": hugo_count,
                "youtube_assignment_count": youtube_count,
                "matched_clip_count": sum(row["disposition"] == "matched" for row in page_records),
                "upload_candidate_count": sum(row["disposition"] == "upload_to_youtube" for row in page_records),
                "restore_candidate_count": sum(row["disposition"] in {"restore_to_hugo", "restore_to_hugo_and_upload"} for row in page_records),
                "manual_review_count": manual_count,
            }
        )
    page_rows.sort(key=lambda row: (str(row["page_status"]), str(row["canonical_page_url"])))
    page_fields = [
        "page_status", "drupal_nid", "page_title", "canonical_page_url",
        "teachinghistory_url", "hugo_content_path", "live_clip_count", "hugo_clip_count",
        "youtube_assignment_count", "matched_clip_count", "upload_candidate_count",
        "restore_candidate_count", "manual_review_count",
    ]
    write_csv(args.output_dir / "video_page_summary.csv", page_rows, page_fields)

    exact_pages = [row for row in page_rows if row["page_status"] == "exact_three_way_match"]
    sample_size = min(12, len(exact_pages))
    sample_indexes = (
        sorted({round(index * (len(exact_pages) - 1) / (sample_size - 1)) for index in range(sample_size)})
        if sample_size > 1
        else ([0] if sample_size else [])
    )
    spot_results = {
        row["drupal_nid"]: row
        for row in read_csv(args.spot_check_results)
    } if args.spot_check_results.exists() else {}
    spot_checks = []
    for index in sample_indexes:
        row = dict(exact_pages[index])
        result = spot_results.get(str(row["drupal_nid"]), {})
        row.update(
            {
                "review_status": result.get("review_status", "Not started"),
                "reviewer": result.get("reviewer", ""),
                "review_notes": result.get("review_notes", ""),
            }
        )
        spot_checks.append(row)
    spot_check_fields = page_fields + ["review_status", "reviewer", "review_notes"]
    write_csv(args.output_dir / "video_spot_check_sample.csv", spot_checks, spot_check_fields)

    disposition_counts = Counter(str(row["disposition"]) for row in reconciliation)
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api": {
            "base_url": args.base_url,
            "targets": len(targets),
            "successful_nodes": sum(str(row["http_status"]) == "200" for row in node_rows),
            "failed_nodes": sum(str(row["http_status"]) != "200" for row in node_rows),
            "live_video_records": len(live_rows),
        },
        "sources": {
            "hugo_video_records": len(hugo_rows),
            "youtube_uploads": len(youtube_rows),
            "server_inventory_files": len(server_rows),
            "server_inventory_error": server_inventory_error,
        },
        "reconciliation_records": len(reconciliation),
        "dispositions": dict(sorted(disposition_counts.items())),
        "upload_queue": len(uploads),
        "restore_queue": len(restores),
        "restore_then_upload_queue": len(restore_then_upload),
        "review_queue": len(reviews),
        "resolved_exceptions": len(resolved_exceptions),
        "upload_sources": {
            "ready_on_server": sum(
                row["upload_status"] == "Ready: source on server"
                for row in reconciliation
            ),
            "source_not_located": sum(
                row["upload_status"] == "Blocked: source not located"
                for row in reconciliation
            ),
        },
        "page_summary": {
            "pages": len(page_rows),
            "exact_three_way_matches": len(exact_pages),
            "needs_reconciliation": len(page_rows) - len(exact_pages),
            "spot_check_sample": len(spot_checks),
        },
    }
    (args.output_dir / "video_reconciliation_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
