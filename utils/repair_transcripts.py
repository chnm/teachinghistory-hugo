#!/usr/bin/env python3
"""Restore complete, readable transcript sections from the Drupal SQL dump."""

import argparse
import re
from pathlib import Path

import yaml

from drupal_to_hugo import (
    SPEAKER_LABEL_RE,
    parse_sql_file,
    transcript_html_to_md,
)


FRONTMATTER_RE = re.compile(r'^---\n(.*?)\n---\n', re.DOTALL)
TRANSCRIPT_HEADING_RE = re.compile(r'^## Transcript\s*$', re.MULTILINE)
NEXT_H2_RE = re.compile(r'^## (?!Transcript\s*$).+$', re.MULTILINE)


def replace_transcript(markdown, transcript):
    """Replace the Transcript section while preserving all other content."""
    heading = TRANSCRIPT_HEADING_RE.search(markdown)
    if not heading:
        return markdown

    following = markdown[heading.end():]
    next_heading = NEXT_H2_RE.search(following)
    section_end = (
        heading.end() + next_heading.start()
        if next_heading else len(markdown)
    )
    suffix = markdown[section_end:].lstrip('\n')

    updated = markdown[:heading.end()].rstrip()
    updated += f'\n\n{transcript.strip()}\n'
    if suffix:
        updated += f'\n{suffix}'
    return updated


def repair_transcripts(content_dir, fields, write=False):
    """Audit or repair Markdown transcript sections from parsed Drupal fields."""
    results = []
    for path in sorted(Path(content_dir).rglob('*.md')):
        markdown = path.read_text(encoding='utf-8')
        if not TRANSCRIPT_HEADING_RE.search(markdown):
            continue

        frontmatter_match = FRONTMATTER_RE.match(markdown)
        if not frontmatter_match:
            results.append((path, None, 'invalid_frontmatter', 0, 0))
            continue

        frontmatter = yaml.safe_load(frontmatter_match.group(1)) or {}
        nid = frontmatter.get('drupal_nid')
        node_fields = fields.get(nid, {})
        items = node_fields.get('field_transcript_text_items')
        if not items:
            value = node_fields.get('field_transcript_text')
            items = value if value else []

        transcript = transcript_html_to_md(items)
        if not transcript:
            results.append((path, nid, 'missing_source', 0, 0))
            continue

        updated = replace_transcript(markdown, transcript)
        status = 'updated' if updated != markdown else 'ok'
        if write and status == 'updated':
            path.write_text(updated, encoding='utf-8')

        speaker_turns = len(SPEAKER_LABEL_RE.findall(transcript))
        delta_count = 1 if isinstance(items, str) else len(items)
        results.append((path, nid, status, delta_count, speaker_turns))

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sql', help='Path to the Drupal SQL dump')
    parser.add_argument('content_dir', help='Path to the Hugo content directory')
    parser.add_argument(
        '--write', action='store_true',
        help='Write repairs; without this flag, perform a dry-run audit.',
    )
    args = parser.parse_args()

    _, fields, *_ = parse_sql_file(args.sql)
    results = repair_transcripts(args.content_dir, fields, write=args.write)

    counts = {}
    for path, nid, status, deltas, speakers in results:
        counts[status] = counts.get(status, 0) + 1
        if status not in {'ok'}:
            print(
                f'{status}: nid={nid} deltas={deltas} '
                f'speaker_turns={speakers} {path}'
            )

    mode = 'repair' if args.write else 'dry run'
    print(f'\nTranscript {mode}: {counts}')


if __name__ == '__main__':
    main()
