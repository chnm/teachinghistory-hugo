#!/usr/bin/env python3
"""
Merge Beyond the Textbook part 1 + part 2 files into single pages.

Part 1 (beyond_the_textbook):
  - Has "What Textbooks Say", "What Historians Say", "What Sources Say" body sections
  - Has question, summary, splash_image fields

Part 2 (beyond_the_textbook_part_2):
  - Has the full essay body
  - Has author_bio, author_image fields

This script:
  1. Matches pairs by title
  2. Parses the three "What X Say" sections from part 1's markdown body
  3. Adds them as YAML frontmatter fields on the part 2 file
  4. Copies question, summary, splash_image from part 1 if missing in part 2
  5. Marks part 1 files as draft: true

Usage:
    python merge_btt_pairs.py --content ../teachinghistory-website/content/history-content/beyond-the-textbook
    python merge_btt_pairs.py --content ../teachinghistory-website/content/history-content/beyond-the-textbook --dry-run
"""

import argparse
import re
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Please install pyyaml: uv pip install pyyaml")
    raise SystemExit(1)


def parse_frontmatter(text):
    """Split Hugo markdown into (frontmatter_dict, body_str)."""
    if not text.startswith('---'):
        return {}, text
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
    """Serialize frontmatter + body back to Hugo markdown."""
    fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False,
                       sort_keys=False)
    result = f"---\n{fm_str}---\n\n"
    if body:
        result += body
    return result


def parse_what_sections(body):
    """Parse ## What Textbooks/Historians/Sources Say sections from markdown body.

    Returns dict with keys: what_textbooks_say, what_historians_say, what_sources_say
    """
    sections = {}
    # Split body into h2 sections
    parts = re.split(r'^## ', body, flags=re.MULTILINE)

    for part in parts[1:]:  # skip content before first ##
        lines = part.strip().split('\n', 1)
        heading = lines[0].strip()
        content = lines[1].strip() if len(lines) > 1 else ''

        if 'textbook' in heading.lower():
            sections['what_textbooks_say'] = content
        elif 'historian' in heading.lower():
            sections['what_historians_say'] = content
        elif 'source' in heading.lower():
            sections['what_sources_say'] = content

    return sections


def main():
    parser = argparse.ArgumentParser(
        description='Merge Beyond the Textbook part 1 + part 2 pairs')
    parser.add_argument('--content', required=True,
                        help='Path to beyond-the-textbook content directory')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would change without writing')
    args = parser.parse_args()

    content_dir = Path(args.content)

    # Index files by content_type
    part1_files = {}  # title → path
    part2_files = {}  # title → path

    for md_file in content_dir.glob('*.md'):
        if md_file.name == '_index.md':
            continue
        text = md_file.read_text(encoding='utf-8')
        fm, _ = parse_frontmatter(text)
        ct = fm.get('content_type', '')
        title = fm.get('title', '')

        if ct == 'beyond_the_textbook':
            part1_files[title] = md_file
        elif ct == 'beyond_the_textbook_part_2':
            part2_files[title] = md_file

    print(f"Found {len(part1_files)} part 1 files, {len(part2_files)} part 2 files\n")

    # Match pairs
    matched = 0
    unmatched_p1 = []
    unmatched_p2 = []

    # Try exact title match first, then fuzzy
    p2_remaining = dict(part2_files)

    for title, p1_path in sorted(part1_files.items()):
        p2_path = p2_remaining.pop(title, None)

        # Fuzzy: try matching on the slug portion of the filename
        if p2_path is None:
            p1_slug = p1_path.stem.rsplit('-', 1)[0]  # remove NID
            for p2_title, p2_candidate in list(p2_remaining.items()):
                p2_slug = p2_candidate.stem.rsplit('-', 1)[0]
                if p1_slug == p2_slug:
                    p2_path = p2_candidate
                    del p2_remaining[p2_title]
                    break

        # Even looser: check if one slug contains the other
        if p2_path is None:
            p1_slug = p1_path.stem.rsplit('-', 1)[0]
            for p2_title, p2_candidate in list(p2_remaining.items()):
                p2_slug = p2_candidate.stem.rsplit('-', 1)[0]
                if p2_slug in p1_slug or p1_slug in p2_slug:
                    p2_path = p2_candidate
                    del p2_remaining[p2_title]
                    break

        if p2_path is None:
            unmatched_p1.append((title, p1_path))
            continue

        matched += 1
        p1_text = p1_path.read_text(encoding='utf-8')
        p2_text = p2_path.read_text(encoding='utf-8')
        p1_fm, p1_body = parse_frontmatter(p1_text)
        p2_fm, p2_body = parse_frontmatter(p2_text)

        # Parse What X Say sections
        what_sections = parse_what_sections(p1_body)

        # Copy fields from part 1 to part 2
        fields_to_copy = ['question', 'summary', 'splash_image', 'splash_image_fid']
        additions = {}
        for key in fields_to_copy:
            if key in p1_fm and key not in p2_fm:
                additions[key] = p1_fm[key]
                p2_fm[key] = p1_fm[key]

        # Add What X Say sections as frontmatter
        for key, val in what_sections.items():
            if key not in p2_fm:
                p2_fm[key] = val

        prefix = "[DRY RUN] " if args.dry_run else ""
        print(f"{prefix}Merging: {title}")
        print(f"  Part 1: {p1_path.name} (NID {p1_fm.get('drupal_nid')})")
        print(f"  Part 2: {p2_path.name} (NID {p2_fm.get('drupal_nid')})")
        if additions:
            print(f"  Copied fields: {', '.join(additions.keys())}")
        if what_sections:
            print(f"  What sections: {', '.join(what_sections.keys())}")

        if not args.dry_run:
            # Write updated part 2
            merged = serialize_file(p2_fm, p2_body)
            p2_path.write_text(merged, encoding='utf-8')

            # Mark part 1 as draft
            p1_fm['draft'] = True
            p1_merged = serialize_file(p1_fm, p1_body)
            p1_path.write_text(p1_merged, encoding='utf-8')

        print()

    # Report
    print(f"{'[DRY RUN] ' if args.dry_run else ''}Results:")
    print(f"  Matched pairs: {matched}")
    if unmatched_p1:
        print(f"  Unmatched part 1:")
        for title, path in unmatched_p1:
            print(f"    {title} ({path.name})")
    if p2_remaining:
        print(f"  Unmatched part 2:")
        for title, path in p2_remaining.items():
            print(f"    {title} ({path.name})")


if __name__ == '__main__':
    main()
