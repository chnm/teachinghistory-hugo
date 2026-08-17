#!/usr/bin/env python3
"""Inventory Hugo content pages that reference playable video assets."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

import yaml


VIDEO_RE = re.compile(
    r"""(?P<src>
        (?:https?://|/|themes/)
        [^\s\])>"']+?
        \.(?:mp4|m4v|mov|webm|ogv)
        (?![a-z0-9])
        (?:[?#][^\s\])>"']*)?
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def split_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    marker = text.find("\n---\n", 4)
    if marker == -1:
        return {}, text
    return yaml.safe_load(text[4:marker]) or {}, text[marker + 5 :]


def fallback_url(path: Path, content_dir: Path) -> str:
    relative = path.relative_to(content_dir).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "_index":
        parts.pop()
    return "/" + "/".join(parts) + ("/" if parts else "")


def clean_source(source: str) -> str:
    # Markdown exports escaped underscores in otherwise ordinary asset paths.
    return source.replace(r"\_", "_")


def inventory(content_dir: Path) -> list[dict[str, str | int]]:
    rows = []
    for path in content_dir.rglob("*.md"):
        metadata, body = split_front_matter(path.read_text(encoding="utf-8"))
        structured = metadata.get("videos") or []
        structured_sources = [
            clean_source(video["src"])
            for video in structured
            if isinstance(video, dict) and video.get("src")
        ]
        body_sources = [clean_source(match.group("src")) for match in VIDEO_RE.finditer(body)]
        sources = list(dict.fromkeys(structured_sources + body_sources))
        if not sources:
            continue

        rows.append(
            {
                "title": str(metadata.get("title") or path.stem),
                "url": str(metadata.get("url") or fallback_url(path, content_dir)),
                "content_path": str(path.relative_to(content_dir)),
                "video_count": len(sources),
                "video_sources": " | ".join(sources),
                "implementation": (
                    "structured video player" if structured_sources else "legacy body reference"
                ),
                "draft": str(bool(metadata.get("draft", False))).lower(),
            }
        )
    return sorted(rows, key=lambda row: (str(row["url"]), str(row["title"])))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--content",
        type=Path,
        default=Path(__file__).parents[1] / "teachinghistory-website" / "content",
        help="Hugo content directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("video_pages.csv"),
        help="CSV output path",
    )
    args = parser.parse_args()

    rows = inventory(args.content.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "title",
                "url",
                "content_path",
                "video_count",
                "video_sources",
                "implementation",
                "draft",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    structured = sum(row["implementation"] == "structured video player" for row in rows)
    legacy = len(rows) - structured
    print(
        f"Wrote {len(rows)} pages to {args.output} "
        f"({structured} structured, {legacy} legacy)."
    )


if __name__ == "__main__":
    main()
