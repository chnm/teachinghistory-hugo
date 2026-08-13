#!/usr/bin/env python3
"""Audit consolidated remediation items against migrated Hugo content.

The normalized tracker remains a planning artifact. This script adds evidence
from the current repository without changing any content files.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
SCALAR_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*?)\s*$", re.MULTILINE)
NID_SUFFIX_RE = re.compile(r"-(\d+)$")
ASSET_KEYS = {"image", "thumbnail", "splash_image"}


@dataclass(frozen=True)
class ContentPage:
    path: Path
    relative_path: str
    url: str
    drupal_nid: str
    body: str
    frontmatter: dict[str, str]


def normalize_url_path(value: str) -> str:
    """Return a comparable path for an absolute or site-relative URL."""
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    path = unquote(parsed.path or value.split("#", 1)[0])
    path = re.sub(r"/{2,}", "/", path)
    if not path.startswith("/"):
        path = f"/{path}"
    return path.rstrip("/") or "/"


def _unquote_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_content_file(path: Path, content_dir: Path) -> ContentPage:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.search(text)
    frontmatter_text = match.group(1) if match else ""
    frontmatter = {
        key: _unquote_scalar(value)
        for key, value in SCALAR_RE.findall(frontmatter_text)
    }
    body = text[match.end():] if match else text
    return ContentPage(
        path=path,
        relative_path=path.relative_to(content_dir).as_posix(),
        url=normalize_url_path(frontmatter.get("url", "")),
        drupal_nid=frontmatter.get("drupal_nid", ""),
        body=body.strip(),
        frontmatter=frontmatter,
    )


def derived_routes(page: ContentPage) -> set[str]:
    """Return routes implied by both frontmatter and Hugo content location."""
    routes = {page.url} if page.url else set()
    relative = Path(page.relative_path)
    if relative.name == "_index.md":
        route_parts = relative.parent.parts
    else:
        route_parts = relative.with_suffix("").parts
    route = normalize_url_path("/" + "/".join(route_parts))
    routes.add(route)

    if relative.name != "_index.md":
        stem = relative.stem
        stripped = NID_SUFFIX_RE.sub("", stem)
        if stripped != stem:
            stripped_parts = (*relative.parent.parts, stripped)
            routes.add(normalize_url_path("/" + "/".join(stripped_parts)))
    return {route for route in routes if route}


def build_content_index(content_dir: Path) -> tuple[dict[str, ContentPage], dict[str, ContentPage]]:
    by_route: dict[str, ContentPage] = {}
    by_nid: dict[str, ContentPage] = {}
    for path in sorted(content_dir.rglob("*.md")):
        page = parse_content_file(path, content_dir)
        for route in derived_routes(page):
            by_route.setdefault(route, page)
        if page.drupal_nid:
            by_nid.setdefault(page.drupal_nid, page)
    return by_route, by_nid


def resolve_page(url: str, by_route: dict[str, ContentPage], by_nid: dict[str, ContentPage]) -> ContentPage | None:
    route = normalize_url_path(url)
    if not route:
        return None
    if route in by_route:
        return by_route[route]
    last_segment = route.rsplit("/", 1)[-1]
    if last_segment.isdigit():
        return by_nid.get(last_segment)
    return None


def normalize_body(value: str) -> str:
    value = re.sub(r"<!--.*?-->", " ", value, flags=re.DOTALL)
    value = re.sub(r"\s+", " ", value)
    return value.strip().casefold()


def has_duplicate_body(body: str) -> bool:
    """Detect repeated substantial sections separated by a Markdown rule."""
    parts = [normalize_body(part) for part in re.split(r"\n\s*---\s*\n", body)]
    substantial = [part for part in parts if len(part) >= 200]
    return len(substantial) != len(set(substantial))


def asset_path(value: str, static_dir: Path) -> Path | None:
    value = value.strip()
    if not value or value.startswith(("http://", "https://", "data:")):
        return None
    parsed = urlparse(value)
    if not parsed.path.startswith("/"):
        return None
    return static_dir / unquote(parsed.path).lstrip("/")


def audit_flags(page: ContentPage, static_dir: Path) -> list[str]:
    flags: list[str] = []
    if page.relative_path != "_index.md" and not page.relative_path.endswith("/_index.md"):
        if len(normalize_body(page.body)) < 200:
            flags.append("short_body")
        if has_duplicate_body(page.body):
            flags.append("duplicate_body")

    missing_assets = []
    for key in sorted(ASSET_KEYS):
        target = asset_path(page.frontmatter.get(key, ""), static_dir)
        if target is not None and not target.exists():
            missing_assets.append(key)
    if missing_assets:
        flags.append("missing_asset:" + "+".join(missing_assets))
    return flags


def audit_tracker(tracker_path: Path, content_dir: Path, static_dir: Path) -> list[dict[str, str]]:
    by_route, by_nid = build_content_index(content_dir)
    with tracker_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    audited = []
    for row in rows:
        page = resolve_page(row.get("URL", ""), by_route, by_nid)
        result = dict(row)
        result["Content File"] = page.relative_path if page else ""
        result["Drupal NID"] = page.drupal_nid if page else ""
        flags = audit_flags(page, static_dir) if page else []
        if row.get("URL", "").strip() and page is None:
            flags.insert(0, "content_not_matched")
        result["Audit Flags"] = "; ".join(flags)
        audited.append(result)
    return audited


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else []
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows: list[dict[str, str]], summary_path: Path) -> None:
    status_counts = Counter(row.get("Status", "") or "Unspecified" for row in rows)
    workstream_counts = Counter(row.get("Workstream", "") or "Unspecified" for row in rows)
    matched = sum(bool(row.get("Content File")) for row in rows)
    flagged = sum(bool(row.get("Audit Flags")) for row in rows)

    lines = [
        "# Content remediation audit",
        "",
        f"- Tracker rows: {len(rows)}",
        f"- Rows matched to Hugo content: {matched}",
        f"- Rows with automated audit flags: {flagged}",
        "",
        "## Status",
        "",
    ]
    lines.extend(f"- {label}: {count}" for label, count in sorted(status_counts.items()))
    lines.extend(["", "## Workstreams", ""])
    lines.extend(f"- {label}: {count}" for label, count in sorted(workstream_counts.items()))
    lines.extend([
        "",
        "Automated flags are evidence for review, not final dispositions. Category-wide and",
        "global rows may not map to a single Markdown file.",
        "",
    ])
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracker", type=Path, default=Path("reports/content_remediation_tracker.csv"))
    parser.add_argument("--content-dir", type=Path, default=Path("teachinghistory-website/content"))
    parser.add_argument("--static-dir", type=Path, default=Path("teachinghistory-website/static"))
    parser.add_argument("--output", type=Path, default=Path("reports/content_remediation_audit.csv"))
    parser.add_argument("--summary", type=Path, default=Path("reports/content_remediation_audit.md"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = audit_tracker(args.tracker, args.content_dir, args.static_dir)
    write_csv(rows, args.output)
    write_summary(rows, args.summary)
    matched = sum(bool(row.get("Content File")) for row in rows)
    flagged = sum(bool(row.get("Audit Flags")) for row in rows)
    print(f"Audited {len(rows)} tracker rows: {matched} matched, {flagged} flagged")


if __name__ == "__main__":
    main()
