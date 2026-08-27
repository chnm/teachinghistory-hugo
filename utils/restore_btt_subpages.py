#!/usr/bin/env python3
"""Restore Beyond-the-Textbook primary sources and bibliographies from Drupal.

The original Drupal pages exposed the essay plus up to six primary-source
subpages and two annotated-bibliography subpages.  The initial Hugo migration
kept only the essay.  This utility reads the surviving Hugo pages, fetches their
Drupal entities, writes structured data under ``data/btt_subpages``, and
downloads the public-file assets referenced by those supplemental fields.

The command is a dry run unless ``--apply`` is supplied::

    .venv/bin/python utils/restore_btt_subpages.py --apply
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import Iterable

import yaml

from fetch_images import parse_frontmatter
from restore_drupal_nodes import (
    BeautifulSoup,
    DrupalClient,
    first_value,
    html_to_md,
    local_file_url,
    localize_markdown_assets,
    parallel_map,
    public_file_relative,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTENT_DIR = (
    REPO_ROOT
    / "teachinghistory-website"
    / "content"
    / "history-content"
    / "beyond-the-textbook"
)
DEFAULT_DATA_DIR = (
    REPO_ROOT / "teachinghistory-website" / "data" / "btt_subpages"
)
DEFAULT_STATIC_ROOT = REPO_ROOT / "teachinghistory-website" / "static"
SOURCE_SUFFIXES = ("title", "annotation", "image", "text", "citation")
STANDALONE_BLOCK = re.compile(r"^(?:#{1,6}\s|!\[|\|)")
SEQUENCE_BLOCK_START = re.compile(r"^(?:[-*+]\s|\d+[.)]\s|>\s?)")


class LiteralDumper(yaml.SafeDumper):
    """Use readable block scalars for recovered multi-paragraph Markdown."""


def _represent_string(dumper, value):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


LiteralDumper.add_representer(str, _represent_string)


def markdown_value(entity: dict, key: str) -> str:
    values = [
        item.get("value", "")
        for item in (entity.get(key) or [])
        if isinstance(item, dict) and item.get("value")
    ]
    if not values:
        return ""
    converted = html_to_md("\n\n".join(values)).strip()
    return localize_markdown_assets(converted)


def normalize_source_text(markdown: str) -> str:
    """Remove archival hard wraps while preserving Markdown block structure."""
    blocks = []
    current = []

    def flush():
        if current:
            blocks.append(" ".join(current))
            current.clear()

    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    for raw_line in normalized.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line.replace("\u00a0", " ")).strip()
        if not line:
            flush()
            continue
        if STANDALONE_BLOCK.match(line):
            flush()
            blocks.append(line)
            continue
        if SEQUENCE_BLOCK_START.match(line) and current:
            flush()
        current.append(line)

    flush()
    return "\n\n".join(blocks)


def plain_title(entity: dict, key: str, fallback: str) -> str:
    value = first_value(entity, key)
    if not value:
        return fallback
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True) or fallback


def extract_btt_subpages(entity: dict, max_sources: int = 10) -> tuple[dict, set[str]]:
    """Return structured Hugo data and relevant Drupal public-file URLs."""
    nid = int(first_value(entity, "nid"))
    data = {"nid": nid, "primary_sources": [], "bibliographies": []}
    assets = set()

    for number in range(1, max_sources + 1):
        prefix = f"field_source{number}_"
        if not any(entity.get(prefix + suffix) for suffix in SOURCE_SUFFIXES):
            continue

        source = {
            "subpage": number,
            "title": plain_title(
                entity, prefix + "title", f"Primary Source {number}"
            ),
        }
        for suffix in ("annotation", "text", "citation"):
            value = markdown_value(entity, prefix + suffix)
            if suffix == "text":
                value = normalize_source_text(value)
            if value:
                source[suffix] = value

        images = entity.get(prefix + "image") or []
        if images and images[0].get("url"):
            item = images[0]
            source["image"] = {
                "url": local_file_url(item["url"]),
                "alt": item.get("alt") or source["title"],
            }
            for dimension in ("width", "height"):
                if item.get(dimension):
                    source["image"][dimension] = int(item[dimension])
            assets.add(item["url"])

        data["primary_sources"].append(source)

    for subpage, key, title in (
        (7, "field_primary_annotated_biblio", "Primary Sources"),
        (8, "field_secondary_annotated_bib", "Secondary Sources"),
    ):
        content = markdown_value(entity, key)
        if content:
            data["bibliographies"].append(
                {"subpage": subpage, "title": title, "content": content}
            )

    # Supplemental HTML can itself contain embedded public-file references.
    for number in range(1, max_sources + 1):
        for suffix in SOURCE_SUFFIXES:
            for item in entity.get(f"field_source{number}_{suffix}") or []:
                value = item.get("value") if isinstance(item, dict) else None
                if not value or "<" not in value:
                    continue
                soup = BeautifulSoup(value, "html.parser")
                for tag in soup.find_all(True):
                    for attribute in ("src", "href", "poster"):
                        candidate = tag.get(attribute)
                        if candidate and public_file_relative(candidate):
                            assets.add(candidate)

    return data, assets


def content_inventory(content_dir: Path) -> list[tuple[Path, int]]:
    records = []
    seen = set()
    for path in sorted(content_dir.glob("*.md")):
        if path.name == "_index.md":
            continue
        frontmatter, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        if frontmatter.get("content_type") != "beyond_the_textbook_part_2":
            continue
        nid = int(frontmatter["drupal_nid"])
        if nid in seen:
            raise ValueError(f"duplicate Beyond-the-Textbook Drupal nid {nid}")
        seen.add(nid)
        records.append((path, nid))
    return records


def serialize_data(data: dict) -> str:
    return yaml.dump(
        data,
        Dumper=LiteralDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=100,
    )


def write_assets(
    asset_urls: Iterable[str],
    client: DrupalClient,
    static_root: Path,
    workers: int,
) -> tuple[int, int]:
    pending = []
    existing = 0
    for source in sorted(set(asset_urls)):
        relative = public_file_relative(source)
        if not relative:
            continue
        destination = static_root / "files" / relative
        if destination.exists():
            existing += 1
        else:
            pending.append((source, destination))

    def download(pair):
        source, destination = pair
        payload = client.asset(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return destination

    parallel_map(pending, download, workers)
    return len(pending), existing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://drupal.teachinghistory.org")
    parser.add_argument("--content-dir", type=Path, default=DEFAULT_CONTENT_DIR)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--static-root", type=Path, default=DEFAULT_STATIC_ROOT)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    records = content_inventory(args.content_dir)
    client = DrupalClient(args.base_url)
    entities = parallel_map([nid for _, nid in records], client.entity, args.workers)
    entities_by_nid = {
        int(first_value(entity, "nid")): entity for entity in entities if entity
    }

    missing = sorted(nid for _, nid in records if nid not in entities_by_nid)
    if missing:
        raise RuntimeError(
            "Drupal entities missing or inaccessible: " + ", ".join(map(str, missing))
        )

    restored = []
    assets = set()
    for path, nid in records:
        data, page_assets = extract_btt_subpages(entities_by_nid[nid])
        if not data["primary_sources"] and not data["bibliographies"]:
            raise RuntimeError(f"node {nid} has no supplemental subpages")
        restored.append((path, data))
        assets.update(page_assets)

    verb = "Restore" if args.apply else "Would restore"
    print(f"{verb} supplemental data for {len(restored)} Beyond-the-Textbook pages:")
    for path, data in restored:
        print(
            f"  {data['nid']}\t{path.name}\t"
            f"{len(data['primary_sources'])} sources\t"
            f"{len(data['bibliographies'])} bibliographies"
        )
    print(
        f"Totals: {sum(len(data['primary_sources']) for _, data in restored)} sources, "
        f"{sum(len(data['bibliographies']) for _, data in restored)} bibliographies, "
        f"{len(assets)} referenced assets"
    )

    if not args.apply:
        print("Dry run; use --apply to write data and assets.")
        return 0

    args.data_dir.mkdir(parents=True, exist_ok=True)
    for _, data in restored:
        destination = args.data_dir / f"nid-{data['nid']}.yaml"
        if destination.exists() and not args.overwrite:
            raise FileExistsError(f"refusing to overwrite {destination}")
        destination.write_text(serialize_data(data), encoding="utf-8")

    downloaded, existing = write_assets(
        assets, client, args.static_root, args.workers
    )
    print(
        f"Wrote {len(restored)} data files; downloaded {downloaded} assets; "
        f"reused {existing} existing assets."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
