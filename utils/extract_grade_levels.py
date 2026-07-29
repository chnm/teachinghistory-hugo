#!/usr/bin/env python3
"""
Extract grade_level and field_target_audience from the Drupal SQL dump
and inject grade_levels into Hugo content frontmatter.

Taxonomy term mapping (from taxonomy_term_field_data):
  35 → K, 36 → 1, 37 → 2, 38 → 3, 39 → 4, 40 → 5,
  41 → 6, 42 → 7, 43 → 8, 47 → 9, 44 → 10, 45 → 11, 46 → 12

Grade ranges for the site:
  elementary: K-5  (tids 35-40)
  middle:     6-8  (tids 41-43)
  high:       9-12 (tids 44-47)
"""

import re
import sys
from pathlib import Path
from collections import defaultdict

# ── Config ──────────────────────────────────────────────────────────────
SQL_FILE = Path(__file__).parent / "th_db.sql"
CONTENT_DIR = Path(__file__).parent.parent / "teachinghistory-website" / "content"

# Taxonomy tid → grade label
TID_TO_GRADE = {
    35: "K", 36: "1", 37: "2", 38: "3", 39: "4", 40: "5",
    41: "6", 42: "7", 43: "8", 47: "9", 44: "10", 45: "11", 46: "12",
}

# Grade label → range bucket
GRADE_TO_RANGE = {
    "K": "elementary", "1": "elementary", "2": "elementary",
    "3": "elementary", "4": "elementary", "5": "elementary",
    "6": "middle", "7": "middle", "8": "middle",
    "9": "high", "10": "high", "11": "high", "12": "high",
}

# Target audience text → range buckets
AUDIENCE_MAP = {
    "elementary": ["elementary"],
    "middle school": ["middle"],
    "high school": ["high"],
    "secondary": ["middle", "high"],
    "kindergarten through twelfth grade": ["elementary", "middle", "high"],
    "fourth grade through twelfth grade": ["elementary", "middle", "high"],
    "fourth grade through eighth grade": ["elementary", "middle"],
    "seventh grade through twelfth grade": ["middle", "high"],
    "eighth grade through twelfth grade": ["middle", "high"],
    "ninth grade through twelfth grade": ["high"],
}


def parse_grade_level_table(sql_path: Path) -> dict[int, set[str]]:
    """Parse node__grade_level INSERT rows → {nid: set of grade labels}."""
    nid_grades: dict[int, set[str]] = defaultdict(set)
    in_insert = False

    with open(sql_path, encoding="utf-8") as f:
        for line in f:
            if "INSERT INTO `node__grade_level` VALUES" in line:
                in_insert = True
                continue
            if in_insert:
                if line.startswith("/*!") or line.startswith("UNLOCK"):
                    break
                # Each row: ('bundle',0,entity_id,revision_id,'lang',delta,grade_level_target_id)
                for match in re.finditer(
                    r"\('[^']*',\d+,(\d+),\d+,'[^']*',\d+,(\d+)\)", line
                ):
                    nid = int(match.group(1))
                    tid = int(match.group(2))
                    grade = TID_TO_GRADE.get(tid)
                    if grade:
                        nid_grades[nid].add(grade)

    return nid_grades


def parse_target_audience_table(sql_path: Path) -> dict[int, set[str]]:
    """Parse node__field_target_audience INSERT rows → {nid: set of range buckets}."""
    nid_ranges: dict[int, set[str]] = defaultdict(set)
    in_insert = False

    with open(sql_path, encoding="utf-8") as f:
        for line in f:
            if "INSERT INTO `node__field_target_audience` VALUES" in line:
                in_insert = True
                continue
            if in_insert:
                if line.startswith("/*!") or line.startswith("UNLOCK"):
                    break
                for match in re.finditer(
                    r"\('[^']*',\d+,(\d+),\d+,'[^']*',\d+,'([^']*)'\)", line
                ):
                    nid = int(match.group(1))
                    audience = match.group(2).lower().strip()
                    ranges = AUDIENCE_MAP.get(audience, [])
                    for r in ranges:
                        nid_ranges[nid].add(r)

    return nid_ranges


def grades_to_ranges(grades: set[str]) -> list[str]:
    """Convert individual grade labels to sorted range buckets."""
    ranges = set()
    for g in grades:
        r = GRADE_TO_RANGE.get(g)
        if r:
            ranges.add(r)
    order = {"elementary": 0, "middle": 1, "high": 2}
    return sorted(ranges, key=lambda x: order.get(x, 99))


def inject_frontmatter(content_dir: Path, nid_to_ranges: dict[int, list[str]], dry_run: bool = False):
    """Walk content files and inject grade_levels into frontmatter."""
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
        ranges = nid_to_ranges.get(nid)
        if not ranges:
            skipped_no_match += 1
            continue

        # Skip if already has grade_levels
        if re.search(r"^grade_levels:", text, re.MULTILINE):
            already_has += 1
            continue

        # Build the YAML list
        yaml_list = "\n".join(f"  - {r}" for r in ranges)
        grade_block = f"grade_levels:\n{yaml_list}"

        # Insert before the closing ---
        # Find the second --- (end of frontmatter)
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue

        new_fm = parts[1].rstrip() + f"\n{grade_block}\n"
        new_text = f"---{new_fm}---{parts[2]}"

        if dry_run:
            print(f"  {md_file.relative_to(content_dir)} → {ranges}")
        else:
            md_file.write_text(new_text, encoding="utf-8")
        updated += 1

    return updated, skipped_no_nid, skipped_no_match, already_has


def main():
    dry_run = "--dry-run" in sys.argv

    print("Parsing node__grade_level table...")
    nid_grades = parse_grade_level_table(SQL_FILE)
    print(f"  Found {len(nid_grades)} nodes with grade_level data")

    print("Parsing node__field_target_audience table...")
    nid_audience = parse_target_audience_table(SQL_FILE)
    print(f"  Found {len(nid_audience)} nodes with target_audience data")

    # Merge: convert grade labels to range buckets, then merge with audience data
    nid_to_ranges: dict[int, list[str]] = {}

    for nid, grades in nid_grades.items():
        nid_to_ranges[nid] = grades_to_ranges(grades)

    for nid, ranges in nid_audience.items():
        if nid in nid_to_ranges:
            # Merge
            existing = set(nid_to_ranges[nid])
            existing.update(ranges)
            order = {"elementary": 0, "middle": 1, "high": 2}
            nid_to_ranges[nid] = sorted(existing, key=lambda x: order.get(x, 99))
        else:
            order = {"elementary": 0, "middle": 1, "high": 2}
            nid_to_ranges[nid] = sorted(ranges, key=lambda x: order.get(x, 99))

    print(f"  Total nodes with grade data: {len(nid_to_ranges)}")

    # Stats on ranges
    range_counts = defaultdict(int)
    for ranges in nid_to_ranges.values():
        for r in ranges:
            range_counts[r] += 1
    for r in ["elementary", "middle", "high"]:
        print(f"    {r}: {range_counts.get(r, 0)} nodes")

    if dry_run:
        print("\n=== DRY RUN ===")

    print(f"\nInjecting grade_levels into {CONTENT_DIR}...")
    updated, no_nid, no_match, already = inject_frontmatter(
        CONTENT_DIR, nid_to_ranges, dry_run=dry_run
    )

    print(f"\nResults:")
    print(f"  Updated:       {updated}")
    print(f"  Already had:   {already}")
    print(f"  No NID:        {no_nid}")
    print(f"  No grade data: {no_match}")


if __name__ == "__main__":
    main()
