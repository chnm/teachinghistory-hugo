#!/usr/bin/env python3
"""
Extract field_time_estimate (duration) from the Drupal SQL dump
and inject into Hugo content frontmatter as 'duration'.

Only applies to lesson_plan_reviews content type.
"""

import re
import sys
from pathlib import Path
from collections import defaultdict

# ── Config ──────────────────────────────────────────────────────────────
SQL_FILE = Path(__file__).parent / "th_db.sql"
CONTENT_DIR = Path(__file__).parent.parent / "teachinghistory-website" / "content"


def parse_time_estimate_table(sql_path: Path) -> dict[int, str]:
    """Parse node__field_time_estimate INSERT rows → {nid: duration string}."""
    nid_duration: dict[int, str] = {}
    in_insert = False

    with open(sql_path, encoding="utf-8") as f:
        for line in f:
            if "INSERT INTO `node__field_time_estimate` VALUES" in line:
                in_insert = True
                continue
            if in_insert:
                if line.startswith("/*!") or line.startswith("UNLOCK"):
                    break
                # Each row: ('bundle',0,entity_id,revision_id,'lang',delta,'value')
                for match in re.finditer(
                    r"\('[^']*',\d+,(\d+),\d+,'[^']*',\d+,'([^']*)'\)", line
                ):
                    nid = int(match.group(1))
                    duration = match.group(2).strip()
                    if duration:
                        nid_duration[nid] = duration

    return nid_duration


def inject_frontmatter(content_dir: Path, nid_to_duration: dict[int, str], dry_run: bool = False):
    """Walk content files and inject duration into frontmatter."""
    updated = 0
    skipped_no_nid = 0
    skipped_no_match = 0
    already_has = 0

    for md_file in content_dir.rglob("*.md"):
        text = md_file.read_text(encoding="utf-8")

        # Extract drupal_nid
        nid_match = re.search(r"^drupal_nid:\s*(\d+)", text, re.MULTILINE)
        if not nid_match:
            skipped_no_nid += 1
            continue

        nid = int(nid_match.group(1))
        duration = nid_to_duration.get(nid)
        if not duration:
            skipped_no_match += 1
            continue

        # Skip if already has duration
        if re.search(r"^duration:", text, re.MULTILINE):
            already_has += 1
            continue

        # Escape single quotes in YAML value
        safe_duration = duration.replace("'", "''")
        duration_line = f"duration: '{safe_duration}'"

        # Insert before the closing ---
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue

        new_fm = parts[1].rstrip() + f"\n{duration_line}\n"
        new_text = f"---{new_fm}---{parts[2]}"

        if dry_run:
            print(f"  {md_file.relative_to(content_dir)} → {duration}")
        else:
            md_file.write_text(new_text, encoding="utf-8")
        updated += 1

    return updated, skipped_no_nid, skipped_no_match, already_has


def main():
    dry_run = "--dry-run" in sys.argv

    print("Parsing node__field_time_estimate table...")
    nid_duration = parse_time_estimate_table(SQL_FILE)
    print(f"  Found {len(nid_duration)} nodes with duration data")

    if dry_run:
        print("\n=== DRY RUN ===")

    print(f"\nInjecting duration into {CONTENT_DIR}...")
    updated, no_nid, no_match, already = inject_frontmatter(
        CONTENT_DIR, nid_duration, dry_run=dry_run
    )

    print(f"\nResults:")
    print(f"  Updated:       {updated}")
    print(f"  Already had:   {already}")
    print(f"  No NID:        {no_nid}")
    print(f"  No duration:   {no_match}")


if __name__ == "__main__":
    main()
