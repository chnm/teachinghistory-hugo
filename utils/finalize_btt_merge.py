# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Finalize the Beyond-the-Textbook merge, preserving old->new redirects.

The BTT content merge already ran: each topic's Part 2 (`beyond_the_textbook_part_2`)
carries the merged `what_*_say` fields and is the surviving page, while Part 1
(`beyond_the_textbook`) was marked `draft: true`. But a draft page is excluded from
the Hugo build, so Part 1's legacy URLs (its `aliases:` path + `/node/{nid}`) fall out
of the redirect manifest and would 404.

This step, per matched pair:
  1. Copies Part 1's legacy URLs onto Part 2's `aliases:` — the Part 1 path-alias AND
     the synthesized `/node/{part1_nid}` — so both old URLs 301 to the merged page.
  2. Renames the surviving Part 2 file to its clean slug (drops the `-{nid}` suffix),
     since the draft Part 1 that forced the collision is being removed.
  3. Deletes the Part 1 draft file (its content lives in Part 2; git keeps history).

Pairing: by clean slug (filename minus `-{nid}`); the single title-mismatched pair is
resolved as the lone remaining Part1/Part2. Every pairing is printed for review.

Idempotent: once Part 1 drafts are gone there is nothing to do.

Usage:
    uv run utils/finalize_btt_merge.py            # Dry run
    uv run utils/finalize_btt_merge.py --apply
"""

import argparse
import re
import sys
from pathlib import Path

BTT_DIR = (Path(__file__).resolve().parent.parent / "teachinghistory-website"
           / "content" / "history-content" / "beyond-the-textbook")


def fm_of(text: str) -> str:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    return m.group(1) if m else ""


def field(fm: str, key: str) -> str:
    m = re.search(rf"^{key}:\s*(.+?)\s*$", fm, re.MULTILINE)
    return m.group(1).strip() if m else ""


def aliases_of(fm: str) -> list[str]:
    m = re.search(r"^aliases:\s*\n((?:[ \t]*-\s*.+\n?)+)", fm, re.MULTILINE)
    if not m:
        return []
    return [re.sub(r"^\s*-\s*", "", ln).strip() for ln in m.group(1).splitlines() if ln.strip()]


def clean_slug(path: Path, fm: str) -> str:
    nid = field(fm, "drupal_nid")
    return re.sub(r"-" + re.escape(nid) + r"$", "", path.stem) if nid else path.stem


def add_aliases(text: str, new: list[str]) -> str:
    """Append alias items after the existing `aliases:` block (deduped)."""
    lines = text.split("\n")
    # end of frontmatter (second '---')
    fm_end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    ai = next((i for i in range(fm_end) if re.match(r"^aliases:\s*$", lines[i])), None)
    if ai is None:  # no aliases block: create one right after the opening '---'
        lines[1:1] = ["aliases:"] + [f"- {a}" for a in new]
        return "\n".join(lines)
    j = ai + 1
    existing = set()
    while j < fm_end and re.match(r"^\s*-\s+", lines[j]):
        existing.add(re.sub(r"^\s*-\s*", "", lines[j]).strip())
        j += 1
    ins = [f"- {a}" for a in new if a not in existing]
    lines[j:j] = ins
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Finalize BTT merge, preserving redirects.")
    ap.add_argument("--apply", action="store_true", help="Apply (default is dry run).")
    args = ap.parse_args()

    if not BTT_DIR.exists():
        print(f"Not found: {BTT_DIR}")
        sys.exit(1)

    part1, part2 = {}, {}  # clean_slug -> (path, fm)
    for p in sorted(BTT_DIR.glob("*.md")):
        if p.name == "_index.md":
            continue
        fm = fm_of(p.read_text(encoding="utf-8"))
        ct = field(fm, "content_type")
        if ct == "beyond_the_textbook":
            part1[clean_slug(p, fm)] = (p, fm)
        elif ct == "beyond_the_textbook_part_2":
            part2[clean_slug(p, fm)] = (p, fm)

    if not part1:
        print("No Part 1 (beyond_the_textbook) files left — nothing to finalize.")
        return

    # Pair by clean slug; resolve the lone title-mismatched pair as the remainder.
    pairs = []
    p1_left = dict(part1)
    p2_left = dict(part2)
    for slug in sorted(part1):
        if slug in p2_left:
            pairs.append((slug, p1_left.pop(slug), p2_left.pop(slug)))
    if len(p1_left) == 1 and len(p2_left) == 1:
        (_, v1), (_, v2) = p1_left.popitem(), p2_left.popitem()
        pairs.append(("(title-mismatch)", v1, v2))

    if p1_left or p2_left:
        print("ABORT: could not pair these unambiguously:")
        for s, (p, _) in {**p1_left}.items():
            print(f"  part1 {p.name}")
        for s, (p, _) in {**p2_left}.items():
            print(f"  part2 {p.name}")
        sys.exit(1)

    verb = "APPLY" if args.apply else "DRY RUN"
    print(f"[{verb}] finalizing {len(pairs)} Beyond-the-Textbook pairs:\n")
    for slug, (p1, p1fm), (p2, p2fm) in pairs:
        p1_nid = field(p1fm, "drupal_nid")
        moved = aliases_of(p1fm) + ([f"/node/{p1_nid}"] if p1_nid else [])
        target = p2.with_name(clean_slug(p2, p2fm) + p2.suffix)
        print(f"  {slug}")
        print(f"    keep  {p2.name}  ->  {target.name}")
        print(f"    +redirects from part1 (nid {p1_nid}): {moved}")
        print(f"    delete {p1.name} (draft)")
        if args.apply:
            new_text = add_aliases(p2.read_text(encoding="utf-8"), moved)
            p2.write_text(new_text, encoding="utf-8")
            p1.unlink()
            if target != p2:
                p2.rename(target)
    print(f"\n{'Applied.' if args.apply else 'Dry run — nothing changed. Use --apply.'}")


if __name__ == "__main__":
    main()
