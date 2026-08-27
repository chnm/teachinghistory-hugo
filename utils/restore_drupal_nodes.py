#!/usr/bin/env python3
"""Restore post-snapshot Drupal nodes through the public entity REST endpoint.

The main SQL snapshot is intentionally immutable.  This utility recovers newer
published nodes from ``/node/{nid}?_format=json``, converts them with the same
HTML/Markdown helpers as the SQL importer, downloads referenced public files,
and writes them into the Hugo content tree.

The command is a dry run unless ``--apply`` is supplied::

    .venv/bin/python utils/restore_drupal_nodes.py \
        --base-url https://drupal.teachinghistory.org \
        --range 25885:25913 --apply
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
import json
import mimetypes
from pathlib import Path, PurePosixPath
import re
import sys
import time
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import yaml

from drupal_to_hugo import (
    IMAGE_FIELD_TABLES,
    LINK_FIELD_TABLES,
    METADATA_FIELD_TABLES,
    TEXT_FIELD_TABLES,
    BeautifulSoup,
    compose_body,
    html_to_md,
    slugify,
)


DEFAULT_CONTENT_ROOT = (
    Path(__file__).resolve().parent.parent / "teachinghistory-website" / "content"
)
DEFAULT_STATIC_ROOT = (
    Path(__file__).resolve().parent.parent / "teachinghistory-website" / "static"
)

CONTENT_DESTINATIONS = {
    "website": "history-content/website-reviews",
    "teaching_guides": "teaching-materials/teaching-guides",
    "blog": "blog",
    "research_tool": "digital-classroom/tech-for-teachers",
    "beyond_the_textbook": "history-content/beyond-the-textbook",
    "beyond_the_textbook_part_2": "history-content/beyond-the-textbook",
}

TAXONOMY_FIELDS = {
    "time_periods": "time_periods",
    "grade_level": "grade_levels",
    "topic": "topics",
    "evidence": "evidence_types",
    "resource_type": "resource_types",
    "keywords": "tags",
    "tags": "tags",
}

IMAGE_KEYS = {
    table.removeprefix("node__"): fm_key
    for table, fm_key in IMAGE_FIELD_TABLES.items()
}
TEXT_KEYS = set(TEXT_FIELD_TABLES.values()) | {"body"}
METADATA_KEYS = {
    table.removeprefix("node__"): fm_key
    for table, fm_key in METADATA_FIELD_TABLES.items()
}
LINK_KEYS = {
    table.removeprefix("node__"): fm_key
    for table, fm_key in LINK_FIELD_TABLES.items()
}

LOCAL_TIMEZONE = ZoneInfo("America/New_York")
PUBLIC_FILES_PREFIX = "/sites/default/files/"
LEGACY_FILES_PREFIX = "/files/"
LEGACY_FILE_HOSTS = {
    "drupal.teachinghistory.org",
    "teachinghistory.org",
    "www.teachinghistory.org",
}


@dataclass
class Page:
    nid: int
    content_type: str
    title: str
    destination: str
    frontmatter: dict
    body: str
    asset_urls: set[str]

    @property
    def slug(self) -> str:
        return slugify(self.title) or f"node-{self.nid}"


def first_value(entity: dict, key: str, default=""):
    values = entity.get(key) or []
    if not values:
        return default
    item = values[0]
    if isinstance(item, dict):
        return item.get("value", default)
    return item


def api_date(value: str) -> str:
    """Match the legacy importer's Eastern-local, timezone-free dates."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(LOCAL_TIMEZONE).replace(tzinfo=None)
    return parsed.isoformat()


def public_file_relative(url: str) -> str | None:
    """Return a safe path below Drupal's public files directory."""
    if not url:
        return None
    parsed = urlparse(url)
    path = unquote(parsed.path)
    if path.startswith(PUBLIC_FILES_PREFIX):
        prefix = PUBLIC_FILES_PREFIX
    elif path.startswith(LEGACY_FILES_PREFIX) and (
        not parsed.hostname or parsed.hostname.lower() in LEGACY_FILE_HOSTS
    ):
        prefix = LEGACY_FILES_PREFIX
    else:
        return None
    relative = path.removeprefix(prefix).lstrip("/")
    pure = PurePosixPath(relative)
    if not relative or pure.is_absolute() or ".." in pure.parts:
        return None
    return str(pure)


def local_file_url(url: str) -> str:
    relative = public_file_relative(url)
    if relative is None:
        return url
    return "/files/" + quote(relative, safe="/")


def download_url(base_url: str, url: str) -> str | None:
    relative = public_file_relative(url)
    if relative is None:
        return None
    return urljoin(base_url.rstrip("/") + "/", PUBLIC_FILES_PREFIX.lstrip("/")) + quote(
        relative, safe="/"
    )


def all_strings(value) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from all_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from all_strings(item)


def collect_asset_urls(entity: dict) -> set[str]:
    """Collect image, attachment, and inline public-file URLs."""
    urls = set()
    for value in all_strings(entity):
        if public_file_relative(value) is not None:
            urls.add(value)
        if "<" not in value:
            continue
        soup = BeautifulSoup(value, "html.parser")
        for tag in soup.find_all(True):
            for attribute in ("src", "href", "poster"):
                candidate = tag.get(attribute)
                if candidate and public_file_relative(candidate) is not None:
                    urls.add(candidate)
    return urls


def localize_markdown_assets(markdown: str) -> str:
    """Point converted Markdown public-file links at Hugo's ``/files`` tree."""
    if not markdown:
        return markdown
    absolute = re.compile(r"https?://[^\s)>]+", re.IGNORECASE)
    markdown = absolute.sub(
        lambda match: local_file_url(match.group(0))
        if public_file_relative(match.group(0)) is not None
        else match.group(0),
        markdown,
    )
    return markdown.replace(PUBLIC_FILES_PREFIX, "/files/")


def text_values(entity: dict, key: str) -> list[str]:
    return [
        item.get("value", "")
        for item in (entity.get(key) or [])
        if isinstance(item, dict) and item.get("value")
    ]


def entity_fields(entity: dict) -> dict:
    """Translate REST field shapes into ``compose_body`` input."""
    fields = {}
    for key in TEXT_KEYS:
        values = text_values(entity, key)
        if values:
            fields[key] = "\n\n".join(values)
            if key == "field_transcript_text":
                fields["field_transcript_text_items"] = [
                    {"delta": index, "value": value}
                    for index, value in enumerate(values)
                ]

    for api_key, field_key in METADATA_KEYS.items():
        value = first_value(entity, api_key)
        if value not in (None, ""):
            fields[field_key] = str(value)

    for api_key, field_key in LINK_KEYS.items():
        links = []
        for delta, item in enumerate(entity.get(api_key) or []):
            uri = item.get("uri") or item.get("url")
            if not uri:
                continue
            link = {"delta": delta, "url": uri}
            if item.get("title"):
                link["title"] = item["title"]
            links.append(link)
        if links:
            fields[field_key] = links
            if api_key == "field_website":
                fields["website_url"] = links[0]["url"]

    attachments = []
    for delta, item in enumerate(
        (entity.get("upload") or []) + (entity.get("field_file_attachments") or [])
    ):
        if item.get("display", True) is False or not item.get("url"):
            continue
        title = item.get("description") or unquote(Path(urlparse(item["url"]).path).name)
        record = {
            "delta": delta,
            "title": title or f"Download {delta + 1}",
            "url": local_file_url(item["url"]),
        }
        mime_type, _ = mimetypes.guess_type(item["url"])
        if mime_type:
            record["mime_type"] = mime_type
        attachments.append(record)
    if attachments:
        fields["attachments"] = attachments

    return fields


def referenced_term_ids(entity: dict) -> set[int]:
    ids = set()
    for api_key in TAXONOMY_FIELDS:
        for item in entity.get(api_key) or []:
            if item.get("target_id") is not None:
                ids.add(int(item["target_id"]))
    return ids


def grade_bands(names: Iterable[str]) -> list[str]:
    bands = set()
    for grade in names:
        if grade in {"K", "1", "2", "3", "4", "5"}:
            bands.add("elementary")
        elif grade in {"6", "7", "8"}:
            bands.add("middle")
        elif grade in {"9", "10", "11", "12"}:
            bands.add("high")
    return sorted(bands)


def entity_taxonomy(entity: dict, term_names: dict[int, str]) -> dict:
    result: dict[str, list[str]] = {}
    for api_key, fm_key in TAXONOMY_FIELDS.items():
        names = [
            term_names[int(item["target_id"])]
            for item in (entity.get(api_key) or [])
            if int(item.get("target_id", -1)) in term_names
        ]
        if api_key == "grade_level":
            names = grade_bands(names)
        else:
            names = sorted(set(names))
        if names:
            result[fm_key] = sorted(set(result.get(fm_key, [])) | set(names))
    return result


def entity_to_page(entity: dict, term_names: dict[int, str]) -> Page:
    nid = int(first_value(entity, "nid"))
    content_type = (entity.get("type") or [{}])[0].get("target_id", "")
    if content_type not in CONTENT_DESTINATIONS:
        raise ValueError(f"unsupported content type {content_type!r} for node {nid}")

    title = first_value(entity, "title") or f"Node {nid}"
    fields = entity_fields(entity)
    body, extra = compose_body(content_type, fields)
    body = localize_markdown_assets(body).strip()

    frontmatter = {
        "title": title,
        "date": api_date(first_value(entity, "created")),
        "lastmod": api_date(first_value(entity, "changed")),
        "content_type": content_type,
        "draft": False,
        "drupal_nid": nid,
    }
    alias = (entity.get("path") or [{}])[0].get("alias")
    if alias:
        frontmatter["aliases"] = [alias]
    if first_value(entity, "promote", False):
        frontmatter["featured"] = True
    if first_value(entity, "sticky", False):
        frontmatter["pinned"] = True
    frontmatter.update({key: value for key, value in extra.items() if value})

    for api_key, fid_key in IMAGE_KEYS.items():
        items = entity.get(api_key) or []
        if not items:
            continue
        item = items[0]
        if item.get("target_id") is not None:
            frontmatter[fid_key] = str(item["target_id"])
        if item.get("url"):
            frontmatter[fid_key.removesuffix("_fid")] = local_file_url(item["url"])

    frontmatter.update(entity_taxonomy(entity, term_names))

    # Keep less common authored metadata even though current templates do not
    # yet render all of it.  This avoids another source-system lookup later.
    for api_key, fm_key in {
        "field_author": "author",
        "field_bibliography": "bibliography",
        "field_primary_annotated_biblio": "primary_annotated_bibliography",
        "field_secondary_annotated_bib": "secondary_annotated_bibliography",
    }.items():
        values = text_values(entity, api_key)
        if values:
            converted = localize_markdown_assets(html_to_md("\n\n".join(values))).strip()
            if converted:
                frontmatter[fm_key] = converted

    return Page(
        nid=nid,
        content_type=content_type,
        title=title,
        destination=CONTENT_DESTINATIONS[content_type],
        frontmatter=frontmatter,
        body=body,
        asset_urls=collect_asset_urls(entity),
    )


def merge_list_field(target: dict, source: dict, key: str):
    values = list(target.get(key, [])) + list(source.get(key, []))
    if values:
        target[key] = list(dict.fromkeys(values))


def merge_sparse_duplicate(sparse: Page, survivor: Page) -> Page:
    """Move an empty duplicate's identity and taxonomy onto its survivor."""
    merge_list_field(survivor.frontmatter, sparse.frontmatter, "aliases")
    aliases = survivor.frontmatter.setdefault("aliases", [])
    node_alias = f"/node/{sparse.nid}"
    if node_alias not in aliases:
        aliases.append(node_alias)
    for key in TAXONOMY_FIELDS.values():
        merge_list_field(survivor.frontmatter, sparse.frontmatter, key)
    survivor.asset_urls.update(sparse.asset_urls)
    return survivor


def merge_btt_pair(part1: Page, part2: Page, part1_entity: dict) -> Page:
    """Create the site's established single-page representation of a BTT pair."""
    merge_sparse_duplicate(part1, part2)
    for key in ("question", "summary", "splash_image", "splash_image_fid"):
        if part1.frontmatter.get(key) and not part2.frontmatter.get(key):
            part2.frontmatter[key] = part1.frontmatter[key]
    for api_key, fm_key in {
        "field_textbook_excerpt": "what_textbooks_say",
        "field_historian_excerpt": "what_historians_say",
        "field_source_excerpt": "what_sources_say",
    }.items():
        values = text_values(part1_entity, api_key)
        if values:
            part2.frontmatter[fm_key] = localize_markdown_assets(
                html_to_md("\n\n".join(values))
            ).strip()
    return part2


def coalesce_pages(pages: list[Page], entities: dict[int, dict]) -> list[Page]:
    """Merge BTT pairs and truly empty exact-title duplicates."""
    by_title: dict[tuple[str, str], list[Page]] = {}
    for page in pages:
        by_title.setdefault((page.destination, page.title), []).append(page)

    result = []
    for group in by_title.values():
        if len(group) == 1:
            result.extend(group)
            continue

        part1 = next((p for p in group if p.content_type == "beyond_the_textbook"), None)
        part2 = next(
            (p for p in group if p.content_type == "beyond_the_textbook_part_2"), None
        )
        if len(group) == 2 and part1 and part2:
            result.append(merge_btt_pair(part1, part2, entities[part1.nid]))
            continue

        empty = [p for p in group if not p.body]
        populated = [p for p in group if p.body]
        if len(group) == 2 and len(empty) == 1 and len(populated) == 1:
            result.append(merge_sparse_duplicate(empty[0], populated[0]))
            continue
        nids = ", ".join(str(page.nid) for page in group)
        raise ValueError(f"ambiguous duplicate title {group[0].title!r}: nodes {nids}")
    return sorted(result, key=lambda page: page.nid)


def serialize_page(page: Page) -> str:
    yaml_text = yaml.dump(
        page.frontmatter,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    result = f"---\n{yaml_text}---\n"
    if page.body:
        result += f"\n{page.body}\n"
    return result


class DrupalClient:
    def __init__(self, base_url: str, attempts: int = 3):
        self.base_url = base_url.rstrip("/")
        self.attempts = attempts

    def _read(self, url: str, accept: str = "application/json") -> bytes:
        request = Request(
            url,
            headers={"Accept": accept, "User-Agent": "TeachingHistory-Hugo/1.0"},
        )
        last_error = None
        for attempt in range(self.attempts):
            try:
                with urlopen(request, timeout=45) as response:
                    return response.read()
            except HTTPError as error:
                if error.code in {403, 404}:
                    raise
                last_error = error
            except URLError as error:
                last_error = error
            if attempt + 1 < self.attempts:
                time.sleep(attempt + 1)
        raise RuntimeError(f"could not fetch {url}: {last_error}")

    def entity(self, nid: int) -> dict | None:
        url = f"{self.base_url}/node/{nid}?_format=json"
        try:
            return json.loads(self._read(url))
        except HTTPError as error:
            # Drupal uses access denied for unpublished/nonexistent nodes on
            # this endpoint, while truly unknown routes return 404.
            if error.code in {403, 404}:
                return None
            raise

    def term_name(self, tid: int) -> tuple[int, str]:
        payload = self._read(
            f"{self.base_url}/taxonomy/term/{tid}", accept="text/html"
        )
        soup = BeautifulSoup(payload, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        name = re.sub(r"\s*\|\s*TeachingHistory\.org\s*$", "", title)
        if not name:
            raise ValueError(f"taxonomy term {tid} has no page title")
        return tid, name

    def asset(self, source_url: str) -> bytes:
        url = download_url(self.base_url, source_url)
        if not url:
            raise ValueError(f"not a Drupal public-file URL: {source_url}")
        return self._read(url, accept="*/*")


def parallel_map(values: Iterable, function: Callable, workers: int) -> list:
    values = list(values)
    if not values:
        return []
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(function, value): value for value in values}
        for future in as_completed(futures):
            results.append(future.result())
    return results


def write_assets(
    pages: list[Page], client: DrupalClient, static_root: Path, workers: int
) -> tuple[int, int]:
    sources = sorted({url for page in pages for url in page.asset_urls})
    pending = []
    existing = 0
    for source in sources:
        relative = public_file_relative(source)
        if relative is None:
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


def parse_range(value: str) -> list[int]:
    match = re.fullmatch(r"(\d+):(\d+)", value)
    if not match:
        raise argparse.ArgumentTypeError("range must be START:END")
    start, end = map(int, match.groups())
    if end < start:
        raise argparse.ArgumentTypeError("range END must not be less than START")
    return list(range(start, end + 1))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://drupal.teachinghistory.org")
    parser.add_argument("--nid", type=int, action="append", default=[])
    parser.add_argument("--range", dest="ranges", type=parse_range, action="append", default=[])
    parser.add_argument("--content-root", type=Path, default=DEFAULT_CONTENT_ROOT)
    parser.add_argument("--static-root", type=Path, default=DEFAULT_STATIC_ROOT)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--apply", action="store_true", help="write content and assets")
    parser.add_argument("--overwrite", action="store_true", help="replace existing page files")
    args = parser.parse_args(argv)

    nids = sorted(set(args.nid + [nid for group in args.ranges for nid in group]))
    if not nids:
        parser.error("provide at least one --nid or --range")

    client = DrupalClient(args.base_url)
    fetched = parallel_map(nids, client.entity, args.workers)
    entities = {
        int(first_value(entity, "nid")): entity
        for entity in fetched
        if entity and first_value(entity, "status", False)
    }
    missing = sorted(set(nids) - set(entities))

    term_ids = sorted({tid for entity in entities.values() for tid in referenced_term_ids(entity)})
    term_names = dict(parallel_map(term_ids, client.term_name, args.workers))

    pages = coalesce_pages(
        [entity_to_page(entity, term_names) for entity in entities.values()], entities
    )
    verb = "Restore" if args.apply else "Would restore"
    print(f"{verb} {len(pages)} Hugo pages from {len(entities)} published Drupal nodes:")
    for page in pages:
        print(f"  {page.nid}\t{page.destination}/{page.slug}.md\t{page.title}")
    if missing:
        print("Missing or unpublished node IDs: " + ", ".join(map(str, missing)))

    if not args.apply:
        print("Dry run; use --apply to write content and assets.")
        return 0

    written = 0
    for page in pages:
        destination = args.content_root / page.destination / f"{page.slug}.md"
        if destination.exists() and not args.overwrite:
            raise FileExistsError(f"refusing to overwrite {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(serialize_page(page), encoding="utf-8")
        written += 1

    downloaded, existing = write_assets(pages, client, args.static_root, args.workers)
    print(f"Wrote {written} pages; downloaded {downloaded} assets; reused {existing} existing assets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
