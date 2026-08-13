#!/usr/bin/env python3
"""
Merge freshly-extracted Drupal content into the existing Hugo site content.

Matches files by drupal_nid in frontmatter.  For each match:
  - Preserves non-empty Markdown bodies unless --replace-body is explicit
  - Fills an empty body during a full merge (not when --keys limits metadata)
  - Merges new frontmatter fields (adds missing keys, does NOT overwrite
    existing keys like title, url, date, etc.)
  - Preserves the file's location in the nested Hugo directory structure

Files in the new extraction that have no match in the existing site are
reported but not copied (they may belong to content types we haven't
organized into sections yet).

Usage:
    python merge_content.py --new content-new --existing ../teachinghistory-website/content
    python merge_content.py --new content-new --existing ../teachinghistory-website/content --write
    python merge_content.py --new content-new --existing ../teachinghistory-website/content --write --replace-body --nids 25836,25163
"""

import argparse
import re
from pathlib import Path
from collections import defaultdict

try:
    import yaml
except ImportError:
    print("Please install pyyaml: uv pip install pyyaml")
    raise SystemExit(1)


def parse_frontmatter(text):
    """Split a Hugo markdown file into (frontmatter_dict, body_str).

    Expects YAML frontmatter delimited by '---'.
    """
    if not text.startswith('---'):
        return {}, text

    # Find second '---'
    end = text.find('---', 3)
    if end == -1:
        return {}, text

    fm_text = text[3:end].strip()
    body = text[end + 3:].lstrip('\n')

    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        fm = {}

    return fm, body


def serialize_file(fm, body):
    """Serialize frontmatter dict + body string back to Hugo markdown."""
    fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False,
                       sort_keys=False)
    result = f"---\n{fm_str}---\n\n"
    if body:
        result += body
    return result


def build_nid_index(content_dir):
    """Build a map of drupal_nid -> file path for all .md files."""
    index = {}
    content_path = Path(content_dir)

    for md_file in content_path.rglob('*.md'):
        # Skip _index.md files (section metadata, not content)
        if md_file.name == '_index.md':
            continue

        try:
            text = md_file.read_text(encoding='utf-8')
        except Exception:
            continue

        fm, _ = parse_frontmatter(text)
        nid = fm.get('drupal_nid')
        if nid is not None:
            index[int(nid)] = md_file

    return index


# Frontmatter keys that should never be overwritten from the new extraction
PROTECTED_KEYS = {
    'title', 'date', 'lastmod', 'type', 'draft', 'drupal_nid',
    'url', 'featured', 'pinned', 'layout', 'weight',
}


def merge_file(existing_path, new_path, dry_run=True, replace_body=False,
               allowed_keys=None):
    """Merge new extraction data into an existing Hugo content file.

    - Body: preserved unless empty or replace_body is explicitly enabled
    - Frontmatter: new keys are added, existing keys preserved
    """
    existing_text = existing_path.read_text(encoding='utf-8')
    new_text = new_path.read_text(encoding='utf-8')

    existing_fm, existing_body = parse_frontmatter(existing_text)
    new_fm, new_body = parse_frontmatter(new_text)

    # Determine what changed
    body_changed = new_body.strip() != existing_body.strip()
    body_gained = bool(new_body.strip()) and not bool(existing_body.strip())

    # Merge frontmatter: add new keys that don't exist yet
    fm_additions = {}
    for key, val in new_fm.items():
        if allowed_keys is not None and key not in allowed_keys:
            continue
        if key not in existing_fm and key not in PROTECTED_KEYS:
            fm_additions[key] = val
            existing_fm[key] = val

    use_new_body = (
        (body_gained and allowed_keys is None)
        or (body_changed and replace_body)
    )

    if not use_new_body and not fm_additions:
        return 'body_diff_skipped' if body_changed else 'unchanged'

    if dry_run:
        if body_gained and use_new_body:
            return 'would_gain_body'
        if use_new_body:
            return 'would_replace_body'
        return 'would_add_metadata'

    # Write merged content
    merged_body = new_body if use_new_body else existing_body
    merged = serialize_file(existing_fm, merged_body)
    existing_path.write_text(merged, encoding='utf-8')

    if body_gained:
        return 'gained_body'
    if use_new_body:
        return 'updated'
    return 'metadata_only'


def main():
    parser = argparse.ArgumentParser(
        description='Merge new Drupal extraction into existing Hugo content')
    parser.add_argument('--new', required=True,
                        help='Path to newly extracted content (e.g. content-new)')
    parser.add_argument('--existing', required=True,
                        help='Path to existing Hugo content (e.g. ../teachinghistory-website/content)')
    parser.add_argument('--write', action='store_true',
                        help='Apply changes (default is a dry run)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Deprecated alias for the default dry-run behavior')
    parser.add_argument('--replace-body', action='store_true',
                        help='Replace non-empty bodies that differ (requires explicit review)')
    parser.add_argument('--nids',
                        help='Comma-separated Drupal NIDs to review or merge')
    parser.add_argument('--keys',
                        help='Only add these comma-separated frontmatter keys')
    args = parser.parse_args()
    dry_run = not args.write or args.dry_run
    selected_nids = None
    if args.nids:
        selected_nids = {int(value.strip()) for value in args.nids.split(',') if value.strip()}
    allowed_keys = None
    if args.keys:
        allowed_keys = {value.strip() for value in args.keys.split(',') if value.strip()}

    print("Building index of existing content by NID...")
    existing_index = build_nid_index(args.existing)
    print(f"  Found {len(existing_index):,} existing files with drupal_nid")

    print("\nBuilding index of new content by NID...")
    new_index = build_nid_index(args.new)
    print(f"  Found {len(new_index):,} new files with drupal_nid")

    # Merge
    results = defaultdict(int)
    gained_types = defaultdict(int)
    unmatched_types = defaultdict(int)

    for nid, new_path in sorted(new_index.items()):
        if selected_nids is not None and nid not in selected_nids:
            continue
        if nid in existing_index:
            existing_path = existing_index[nid]
            status = merge_file(
                existing_path,
                new_path,
                dry_run=dry_run,
                replace_body=args.replace_body,
                allowed_keys=allowed_keys,
            )
            results[status] += 1

            if status not in ('unchanged',):
                print(f"  {nid}: {status:18s} {existing_path}")

            if status in ('gained_body', 'would_gain_body'):
                # Track which content types gained body content
                new_text = new_path.read_text(encoding='utf-8')
                fm, _ = parse_frontmatter(new_text)
                ctype = fm.get('type', 'unknown')
                gained_types[ctype] += 1
        else:
            results['no_match'] += 1
            # Track unmatched by parent dir
            parent = new_path.parent.name
            unmatched_types[parent] += 1

    # Report
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"\n{prefix}Merge results:")
    print(f"  Unchanged:          {results.get('unchanged', 0):,}")
    print(f"  Replaced body:      {results.get('updated', 0) + results.get('would_replace_body', 0):,}")
    print(f"  Gained body (new!): {results.get('gained_body', 0) + results.get('would_gain_body', 0):,}")
    print(f"  Metadata only:      {results.get('metadata_only', 0) + results.get('would_add_metadata', 0):,}")
    print(f"  Body diff skipped:  {results.get('body_diff_skipped', 0):,}")
    print(f"  No match in Hugo:   {results.get('no_match', 0):,}")

    if gained_types:
        print(f"\n{prefix}Content types that gained body content:")
        for ctype, count in sorted(gained_types.items(), key=lambda x: -x[1]):
            print(f"  {ctype:40s}: {count:,}")

    if unmatched_types:
        print(f"\nUnmatched files by directory (not in Hugo site):")
        for dirname, count in sorted(unmatched_types.items(), key=lambda x: -x[1]):
            print(f"  {dirname:40s}: {count:,}")


if __name__ == '__main__':
    main()
