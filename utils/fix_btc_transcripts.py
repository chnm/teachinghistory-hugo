#!/usr/bin/env python3
"""
Targeted fix for 5 Beyond the Chalkboard pages whose body content was
incorrectly extracted as raw video-player markup instead of transcript text.

Reads field_video_overview and field_transcript_text from th_db.sql for the
affected node IDs and rewrites the markdown files with the correct body.
"""

import re
import sys
from pathlib import Path

# Reuse the SQL parsing and HTML→MD helpers from the main extraction script
from drupal_to_hugo import (
    extract_row_tuples,
    parse_field_value,
    html_to_md,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SQL_FILE = Path(__file__).parent / 'th_db.sql'
CONTENT_DIR = (
    Path(__file__).parent.parent
    / 'teachinghistory-website'
    / 'content'
    / 'digital-classroom'
    / 'beyond-the-chalkboard'
)

# Node IDs → markdown filenames
TARGET_NODES = {
    25781: 'analyzing-campaign-commercials-25781.md',
    25783: 'creating-campaign-commercials-25783.md',
    25640: 'recording-experiences-with-first-graders-25640.md',
    24589: 'voicethread-in-a-1st-grade-classroom-24589.md',
    24158: 'zoom-in-inquiry-24158.md',
}

TARGET_NIDS = set(TARGET_NODES.keys())

# SQL tables to scan
TABLES = {
    'node__field_video_overview': 'overview',
    'node__field_transcript_text': 'transcript',
}


# ---------------------------------------------------------------------------
# Extract fields from SQL dump
# ---------------------------------------------------------------------------

def extract_fields_from_sql():
    """Scan th_db.sql for the two target tables and pull rows for our node IDs.

    Returns dict: {nid: {'overview': str, 'transcript': str}}
    """
    data = {nid: {} for nid in TARGET_NIDS}

    current_table = None
    buffer = []

    with open(SQL_FILE, 'r', errors='replace') as f:
        for line in f:
            # Detect INSERT INTO for our target tables
            for sql_table, field_key in TABLES.items():
                if f'INSERT INTO `{sql_table}`' in line:
                    # Flush any previous buffer
                    if current_table and buffer:
                        _process_insert(buffer, current_table, data)
                    current_table = field_key
                    buffer = [line]
                    break
            else:
                if current_table:
                    buffer.append(line)
                    # End of INSERT statement
                    if line.rstrip().endswith(';'):
                        _process_insert(buffer, current_table, data)
                        current_table = None
                        buffer = []

    # Flush remaining
    if current_table and buffer:
        _process_insert(buffer, current_table, data)

    return data


def _process_insert(lines, field_key, data):
    """Parse INSERT lines and extract values for target node IDs."""
    full_text = ''.join(lines)
    match = re.search(r'VALUES\s+(.+);?\s*$', full_text, re.DOTALL)
    if not match:
        return

    rows = extract_row_tuples(match.group(1).rstrip(';'))
    for row in rows:
        if len(row) < 7:
            continue
        try:
            nid = int(parse_field_value(row[2]))
        except (ValueError, TypeError):
            continue

        if nid not in TARGET_NIDS:
            continue

        val = parse_field_value(row[6])
        if not val:
            continue

        # Concatenate multi-delta rows (transcripts have delta 0, 1, 2, …)
        existing = data[nid].get(field_key)
        if existing:
            data[nid][field_key] = existing + '\n\n' + val
        else:
            data[nid][field_key] = val


# ---------------------------------------------------------------------------
# Rewrite markdown files
# ---------------------------------------------------------------------------

def rewrite_md(filepath, new_body):
    """Replace everything after the YAML frontmatter closing --- with new_body."""
    text = filepath.read_text(encoding='utf-8')

    # Find the second '---' (closing frontmatter delimiter)
    first = text.index('---')
    second = text.index('---', first + 3)
    frontmatter = text[:second + 3]

    filepath.write_text(frontmatter + '\n\n' + new_body.strip() + '\n', encoding='utf-8')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not SQL_FILE.exists():
        print(f"ERROR: SQL file not found: {SQL_FILE}")
        sys.exit(1)

    print(f"Reading {SQL_FILE.name} …")
    data = extract_fields_from_sql()

    updated = 0
    for nid, filename in TARGET_NODES.items():
        filepath = CONTENT_DIR / filename
        if not filepath.exists():
            print(f"  SKIP {filename} — file not found")
            continue

        overview_html = data[nid].get('overview', '')
        transcript_html = data[nid].get('transcript', '')

        if not overview_html and not transcript_html:
            print(f"  SKIP {filename} (nid {nid}) — no content found in SQL")
            continue

        # Convert HTML → Markdown
        overview_md = html_to_md(overview_html)
        transcript_md = html_to_md(transcript_html)

        # Compose body: overview first, then transcript
        parts = []
        if overview_md:
            parts.append(overview_md.strip())
        if transcript_md:
            parts.append(transcript_md.strip())
        body = '\n\n---\n\n'.join(parts)

        rewrite_md(filepath, body)
        updated += 1
        print(f"  FIXED {filename} (nid {nid})")

    print(f"\nDone — {updated}/{len(TARGET_NODES)} files updated.")


if __name__ == '__main__':
    main()
