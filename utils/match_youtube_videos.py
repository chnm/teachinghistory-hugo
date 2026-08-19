#!/usr/bin/env python3
"""Infer which TeachingHistory.org page belongs to each channel upload."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

import yaml


SERIES_PREFIXES = (
    "examples of historical thinking",
    "teaching in action",
    "project spotlight",
    "using primary sources",
)
STOP_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "part",
    "the",
    "to",
    "video",
    "with",
}
NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
}


def normalize(value: str) -> str:
    value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode()
        .lower()
        .replace("&", " and ")
    )
    value = re.sub(r"['’]s\b", "s", value)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def strip_series(value: str) -> str:
    value = normalize(value)
    for prefix in SERIES_PREFIXES:
        value = re.sub(rf"^{re.escape(prefix)}\s*", "", value)
    return value


def named_series_subject(value: str) -> str:
    parts = re.split(r"\s+[-–—]\s+", value, maxsplit=2)
    if len(parts) >= 2 and normalize(parts[0]) in SERIES_PREFIXES:
        return normalize(parts[1])
    return ""


def meaningful_tokens(value: str) -> set[str]:
    return {
        token
        for token in normalize(value).split()
        if token not in STOP_WORDS and len(token) > 1
    }


def token_overlap(left: str, right: str) -> float:
    a, b = meaningful_tokens(left), meaningful_tokens(right)
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def sequence_number(value: str) -> int | None:
    tokens = normalize(value).split()
    if not tokens:
        return None
    if tokens[-1].isdigit():
        return int(tokens[-1])
    return NUMBER_WORDS.get(tokens[-1])


def sql_table_rows(sql: str, table: str) -> list[tuple[str, int, int, str]]:
    marker = f"INSERT INTO `{table}` VALUES"
    start = sql.find(marker)
    if start == -1:
        return []
    end = sql.find("UNLOCK TABLES;", start)
    pattern = re.compile(
        r"^\('([^']*)',\d+,(\d+),\d+,'[^']*',(\d+),'((?:\\'|[^'])*)'\)[,;]?$",
        re.MULTILINE,
    )
    return [
        (bundle, int(nid), int(delta), value.replace(r"\'", "'"))
        for bundle, nid, delta, value in pattern.findall(sql[start:end])
    ]


def split_front_matter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    marker = text.find("\n---\n", 4)
    if marker == -1:
        return {}
    try:
        return yaml.safe_load(text[4:marker]) or {}
    except yaml.YAMLError:
        return {}


def page_metadata(repo_dir: Path) -> dict[int, dict[str, str]]:
    pages: dict[int, dict[str, str]] = {}
    roots = (
        (repo_dir / "utils" / "content", False),
        (repo_dir / "utils" / "content-new", False),
        (repo_dir / "teachinghistory-website" / "content", True),
    )
    for root, in_hugo in roots:
        for path in root.rglob("*.md"):
            metadata = split_front_matter(path.read_text(encoding="utf-8", errors="replace"))
            if not metadata.get("drupal_nid"):
                continue
            pages[int(metadata["drupal_nid"])] = {
                "page_title": str(metadata.get("title", "")),
                "page_url": str(metadata.get("url", "")),
                "in_hugo_content": str(in_hugo).lower(),
                "hugo_content_path": (
                    str(path.relative_to(root)) if in_hugo else ""
                ),
            }
    return pages


def video_candidates(
    repo_dir: Path, drupal_inventory: Path
) -> list[dict[str, str | int]]:
    sql = (repo_dir / "utils" / "th_db.sql").read_text(
        encoding="utf-8", errors="replace"
    )
    titles = {
        (nid, delta): value
        for _, nid, delta, value in sql_table_rows(sql, "node__field_video_title")
    }
    pages = page_metadata(repo_dir)
    candidates: list[dict[str, str | int]] = []
    for bundle, nid, delta, asset in sql_table_rows(
        sql, "node__field_video_clip_name"
    ):
        page = pages.get(nid, {})
        candidates.append(
            {
                "drupal_nid": nid,
                "drupal_content_type": bundle,
                "page_title": page.get("page_title", ""),
                "page_url": page.get("page_url", "") or f"/node/{nid}",
                "clip_index": delta + 1,
                "clip_title": titles.get((nid, delta), ""),
                "asset_name": Path(asset).stem,
                "in_hugo_content": page.get("in_hugo_content", "false"),
                "hugo_content_path": page.get("hugo_content_path", ""),
                "rendered_on_live_page": "false",
            }
        )

    def inventory_key(nid: int, asset: str, page_url: str) -> tuple[str, str]:
        # Special pages have no Drupal nid, so their URL must distinguish assets
        # reused across several introduction pages.
        page_key = str(nid) if nid else normalized_page_path(page_url)
        return page_key, normalize(asset)

    by_key = {
        inventory_key(
            int(candidate["drupal_nid"]),
            str(candidate["asset_name"]),
            str(candidate["page_url"]),
        ): candidate
        for candidate in candidates
        if candidate["drupal_nid"]
    }
    with drupal_inventory.open(encoding="utf-8", newline="") as source:
        for page in csv.DictReader(source):
            nid = int(page["drupal_nid"]) if page["drupal_nid"] else 0
            for index, video_source in enumerate(
                page["live_video_sources"].split(" | "), start=1
            ):
                asset = Path(video_source).stem
                key = inventory_key(nid, asset, page["url"])
                if key in by_key:
                    by_key[key]["rendered_on_live_page"] = "true"
                    by_key[key]["page_url"] = page["url"]
                    continue
                candidate = {
                    "drupal_nid": nid or "",
                    "drupal_content_type": page["drupal_content_type"],
                    "page_title": page["title"],
                    "page_url": page["url"],
                    "clip_index": index,
                    "clip_title": (
                        page["title"] if int(page["live_video_count"]) == 1 else ""
                    ),
                    "asset_name": asset,
                    "in_hugo_content": page["in_hugo_content"],
                    "hugo_content_path": page["hugo_content_path"],
                    "rendered_on_live_page": "true",
                }
                candidates.append(candidate)
                by_key[key] = candidate
    return candidates


def load_youtube(path: Path) -> list[dict[str, str]]:
    videos = []
    for line in path.read_text(encoding="utf-8").splitlines():
        video_id, title, duration, upload_date = line.split(r"\t")
        videos.append(
            {
                "youtube_id": video_id,
                "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
                "youtube_title": title,
                "duration": duration,
                "upload_date": "" if upload_date == "NA" else upload_date,
            }
        )
    return videos


def description_page_urls(info_dir: Path | None) -> dict[str, str]:
    """Return the first TeachingHistory.org URL found in each saved description."""
    if not info_dir:
        return {}
    urls = {}
    pattern = re.compile(
        r"https?://(?:www\.)?teachinghistory\.org/[^\s<>)\]]+",
        re.IGNORECASE,
    )
    for path in info_dir.glob("*.info.json"):
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        match = pattern.search(metadata.get("description") or "")
        if match:
            urls[str(metadata.get("id") or path.name.split(".", 1)[0])] = (
                match.group(0).rstrip(".,;:")
            )
    return urls


def normalized_page_path(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    path = parsed.path if parsed.scheme or parsed.netloc else value.split("?", 1)[0]
    return "/" + path.strip("/")


def comparable_page_path(value: str) -> str:
    path = normalized_page_path(value)
    # Visiting History moved under /teaching-materials in the current site.
    if path.startswith("/teaching-materials/visiting-history/"):
        return path.removeprefix("/teaching-materials")
    return path


def description_matches_candidate(
    description_url: str, candidate: dict[str, str | int]
) -> bool:
    if not description_url:
        return False
    description_path = comparable_page_path(description_url)
    candidate_path = comparable_page_path(str(candidate["page_url"]))
    if description_path == candidate_path:
        return True
    final_segment = description_path.rsplit("/", 1)[-1]
    return bool(
        final_segment.isdigit()
        and candidate["drupal_nid"]
        and int(candidate["drupal_nid"]) == int(final_segment)
    )


def add_description_page_candidates(
    candidates: list[dict[str, str | int]], youtube: list[dict[str, str]]
) -> None:
    """Add page-only candidates for description URLs absent from video fields."""
    known_paths = {
        comparable_page_path(str(candidate["page_url"])) for candidate in candidates
    }
    for video in youtube:
        description_url = video["description_page_url"]
        page_path = comparable_page_path(description_url)
        if not page_path or page_path in known_paths:
            continue
        final_segment = page_path.rsplit("/", 1)[-1]
        nid: int | str = int(final_segment) if final_segment.isdigit() else ""
        title = re.sub(
            r"\s+(?:\d+|" + "|".join(NUMBER_WORDS) + r")$",
            "",
            strip_series(video["youtube_title"]),
            flags=re.IGNORECASE,
        ).title()
        candidates.append(
            {
                "drupal_nid": nid,
                "drupal_content_type": (
                    page_path.strip("/").split("/")[-2]
                    if "/" in page_path.strip("/")
                    else "page"
                ),
                "page_title": title,
                "page_url": normalized_page_path(description_url),
                "clip_index": sequence_number(video["youtube_title"]) or 1,
                "clip_title": "",
                "asset_name": "",
                "in_hugo_content": "false",
                "hugo_content_path": "",
                "rendered_on_live_page": "false",
            }
        )
        known_paths.add(page_path)


def score_candidate(
    youtube_title: str,
    candidate: dict[str, str | int],
    clip_frequency: Counter,
    description_url: str = "",
) -> tuple[float, str]:
    youtube = normalize(youtube_title)
    short_youtube = strip_series(youtube_title)
    asset = normalize(str(candidate["asset_name"]))
    clip = normalize(str(candidate["clip_title"]))
    page = normalize(str(candidate["page_title"]))
    page_overlap = token_overlap(page, youtube)
    clip_overlap = token_overlap(clip, youtube)
    series_subject = named_series_subject(youtube_title)
    clip_specificity = len(meaningful_tokens(clip))
    live_bonus = 0.8 if candidate["rendered_on_live_page"] == "true" else 0.0
    score, method = 0.0, "fuzzy title"

    if youtube == asset or short_youtube == asset:
        score, method = 99.0 + live_bonus, "exact legacy asset name"

    if clip and (youtube == clip or short_youtube == clip) and score < 99.0:
        score = 99.0 if clip_frequency[clip] == 1 else 91.0 + page_overlap * 6
        method = "exact clip title" if score == 99.0 else "ambiguous clip title"

    if clip and clip in youtube:
        if clip_frequency[clip] == 1 and youtube.endswith(clip):
            contained_score = 97.5 + min(1.5, page_overlap * 1.5)
            score, method = max(score, contained_score), (
                "upload title ends with exact clip title"
            )
        elif clip_frequency[clip] == 1 and clip_specificity >= 3:
            contained_score = 97.0 + min(2.0, page_overlap * 2.0)
            score, method = max(score, contained_score), (
                "clip title contained in upload title"
            )
        elif page_overlap >= 0.4:
            contained_score = 96.0 + min(2.0, page_overlap * 2.0)
            score, method = max(score, contained_score), "page and clip title"

    number = sequence_number(short_youtube)
    if (
        number == int(candidate["clip_index"])
        and page_overlap >= 0.5
        and score < 98.0
    ):
        score, method = 98.0 + min(1.0, page_overlap), (
            "page title and clip sequence"
        )

    if page_overlap >= 0.75 and clip_overlap >= 0.65 and score < 97.0:
        score, method = 97.0, "strong page and clip similarity"
    elif page_overlap >= 0.55 and clip_overlap >= 0.65 and score < 94.0:
        score, method = 94.0, "page and clip similarity"

    if (
        len(meaningful_tokens(series_subject)) >= 2
        and meaningful_tokens(series_subject) <= meaningful_tokens(page)
        and score < 97.0
    ):
        score, method = 97.0 + min(1.0, clip_overlap), "named series page"

    if score < 90.0:
        forms = [asset, clip, f"{page} {clip}", f"{strip_series(page)} {clip}"]
        similarity = max(
            (
                SequenceMatcher(None, short_youtube, form).ratio()
                for form in forms
                if form
            ),
            default=0.0,
        )
        score = max(score, similarity * 89.0)

    if description_matches_candidate(description_url, candidate):
        # An original page URL in the uploader's description is direct evidence.
        # Retain the title score to rank clips when that page contains several.
        score = 110.0 + min(score, 100.0) / 10.0
        method = f"description URL + {method}" if method else "description URL"
    return score, method


def main() -> None:
    utility_dir = Path(__file__).resolve().parent
    repo_dir = utility_dir.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--youtube-tsv",
        type=Path,
        required=True,
        help="yt-dlp flat-playlist output using literal backslash-t separators",
    )
    parser.add_argument(
        "--drupal-inventory",
        type=Path,
        default=utility_dir / "drupal_video_pages.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=utility_dir / "youtube_video_page_matches.csv",
    )
    parser.add_argument(
        "--page-output",
        type=Path,
        default=utility_dir / "youtube_page_video_matches.csv",
    )
    parser.add_argument(
        "--youtube-info-dir",
        type=Path,
        help="Optional directory of yt-dlp .info.json files with descriptions",
    )
    args = parser.parse_args()

    candidates = video_candidates(repo_dir, args.drupal_inventory)
    youtube = load_youtube(args.youtube_tsv)
    description_urls = description_page_urls(args.youtube_info_dir)
    for video in youtube:
        video["description_page_url"] = description_urls.get(video["youtube_id"], "")
    add_description_page_candidates(candidates, youtube)
    clip_frequency = Counter(
        normalize(str(candidate["clip_title"]))
        for candidate in candidates
        if candidate["clip_title"]
    )

    ranked: list[list[tuple[float, str, int]]] = []
    for video in youtube:
        choices = sorted(
            (
                (
                    *score_candidate(
                        video["youtube_title"],
                        candidate,
                        clip_frequency,
                        video["description_page_url"],
                    ),
                    index,
                )
                for index, candidate in enumerate(candidates)
            ),
            reverse=True,
        )
        ranked.append(choices)

    rows = []
    for video_index, video in enumerate(youtube):
        choices = ranked[video_index]
        score, method, candidate_index = choices[0]

        second_score = max(
            candidate_score
            for candidate_score, _, index in choices
            if index != candidate_index
        )
        margin = score - second_score
        if method.startswith("description URL"):
            confidence = "high"
        elif score >= 97 and (
            margin >= 0.5
            or method
            in {
                "exact legacy asset name",
                "exact clip title",
                "page and clip title",
                "page title and clip sequence",
                "strong page and clip similarity",
                "named series page",
                "upload title ends with exact clip title",
            }
        ):
            confidence = "high"
        elif score >= 90 and margin >= 0:
            confidence = "medium"
        else:
            confidence = "review"
        candidate = candidates[candidate_index]
        rows.append(
            {
                **video,
                **candidate,
                "match_confidence": confidence,
                "match_score": f"{score:.1f}",
                "next_best_margin": f"{margin:.1f}",
                "match_method": method,
            }
        )

    assignment_counts = Counter(
        (
            str(row["drupal_nid"]),
            str(row["page_url"]),
            normalize(str(row["asset_name"])),
        )
        for row in rows
    )
    for row in rows:
        upload_count = assignment_counts[
            (
                str(row["drupal_nid"]),
                str(row["page_url"]),
                normalize(str(row["asset_name"])),
            )
        ]
        row["candidate_upload_count"] = upload_count
        row["possible_duplicate_upload"] = str(upload_count > 1).lower()

    fieldnames = [
        "youtube_id",
        "youtube_url",
        "youtube_title",
        "duration",
        "upload_date",
        "description_page_url",
        "drupal_nid",
        "drupal_content_type",
        "page_title",
        "page_url",
        "clip_index",
        "clip_title",
        "asset_name",
        "in_hugo_content",
        "hugo_content_path",
        "rendered_on_live_page",
        "match_confidence",
        "match_score",
        "next_best_margin",
        "match_method",
        "candidate_upload_count",
        "possible_duplicate_upload",
    ]
    with args.output.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    page_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        page_groups[(str(row["drupal_nid"]), str(row["page_url"]))].append(row)
    page_fieldnames = [
        "drupal_nid",
        "page_title",
        "page_url",
        "drupal_content_type",
        "hugo_content_path",
        "in_hugo_content",
        "rendered_on_live_page",
        "youtube_video_count",
        "confidence_counts",
        "youtube_titles",
        "youtube_urls",
    ]
    with args.page_output.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=page_fieldnames)
        writer.writeheader()
        for page_rows in sorted(
            page_groups.values(),
            key=lambda group: (
                normalize(str(group[0]["page_title"])),
                str(group[0]["page_url"]),
            ),
        ):
            first = page_rows[0]
            confidence_counts = Counter(
                str(row["match_confidence"]) for row in page_rows
            )
            writer.writerow(
                {
                    "drupal_nid": first["drupal_nid"],
                    "page_title": first["page_title"],
                    "page_url": first["page_url"],
                    "drupal_content_type": first["drupal_content_type"],
                    "hugo_content_path": first["hugo_content_path"],
                    "in_hugo_content": first["in_hugo_content"],
                    "rendered_on_live_page": first["rendered_on_live_page"],
                    "youtube_video_count": len(page_rows),
                    "confidence_counts": " | ".join(
                        f"{name}:{count}"
                        for name, count in sorted(confidence_counts.items())
                    ),
                    "youtube_titles": " | ".join(
                        str(row["youtube_title"]) for row in page_rows
                    ),
                    "youtube_urls": " | ".join(
                        str(row["youtube_url"]) for row in page_rows
                    ),
                }
            )

    counts = Counter(row["match_confidence"] for row in rows)
    unique_pages = len(
        {
            (str(row["drupal_nid"]), str(row["page_url"]))
            for row in rows
            if row["page_url"]
        }
    )
    print(
        f"Wrote {len(rows)} YouTube matches across {unique_pages} pages to "
        f"{args.output} and {args.page_output}: "
        + ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
    )


if __name__ == "__main__":
    main()
