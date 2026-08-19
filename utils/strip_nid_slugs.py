# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Rename content files to drop the trailing `-{drupal_nid}` from their slug, so Hugo
serves clean native URLs (e.g. `.../statistics-in-schools/` instead of
`.../statistics-in-schools-25863/`). The Drupal node id stays in `drupal_nid`
frontmatter, so the Caddy redirect pipeline (utils/redirect_mapper.py) is unaffected
and regenerates the legacy->native map from the new native URLs.

Collision handling: within a directory, some Drupal nodes share a title and therefore
a clean slug (e.g. Beyond-the-Textbook pairs). Those files KEEP their `-{nid}` suffix
so every URL stays unique and stable; they are reported so you can review them.

Idempotent: a file already at its clean name is skipped, so re-running is a no-op.

Usage:
    uv run utils/strip_nid_slugs.py            # Dry run: report renames + collisions
    uv run utils/strip_nid_slugs.py --apply    # Rename files
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

CONTENT_DIR = Path(__file__).resolve().parent.parent / "teachinghistory-website" / "content"
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
NID_RE = re.compile(r"^drupal_nid:\s*(\d+)\s*$", re.MULTILINE)


def clean_stem(md_file: Path) -> str:
    """The file's stem with a trailing `-{drupal_nid}` removed (if present)."""
    stem = md_file.stem
    m = FRONTMATTER_RE.match(md_file.read_text(encoding="utf-8"))
    if not m:
        return stem
    nid_m = NID_RE.search(m.group(1))
    if not nid_m:
        return stem
    return re.sub(r"-" + re.escape(nid_m.group(1)) + r"$", "", stem)


def plan_renames() -> tuple[list[tuple[Path, Path]], list[tuple[str, list[str]]]]:
    """Return (renames, collisions). renames = [(src, dst)]; collisions = [(dir/slug, [files])]."""
    files = [p for p in CONTENT_DIR.rglob("*.md") if p.name != "_index.md"]
    groups: dict[tuple[str, str], list[Path]] = defaultdict(list)
    clean_of: dict[Path, str] = {}
    for p in files:
        c = clean_stem(p)
        clean_of[p] = c
        groups[(str(p.parent), c)].append(p)

    renames, collisions = [], []
    for (parent, clean), members in groups.items():
        if len(members) > 1:
            collisions.append((
                str(Path(parent).relative_to(CONTENT_DIR)) + "/" + clean,
                sorted(m.name for m in members),
            ))
            continue  # keep -{nid} on all colliding members
        p = members[0]
        if clean_of[p] != p.stem:
            renames.append((p, p.with_name(clean + p.suffix)))
    renames.sort(key=lambda t: str(t[0]))
    collisions.sort()
    return renames, collisions


def run(apply: bool):
    if not CONTENT_DIR.exists():
        print(f"Content directory not found: {CONTENT_DIR}")
        sys.exit(1)

    renames, collisions = plan_renames()

    # Safety: never overwrite an existing target.
    conflicts = [(s, d) for s, d in renames if d.exists()]
    if conflicts:
        print(f"ABORT: {len(conflicts)} target names already exist:")
        for s, d in conflicts[:20]:
            print(f"  {s.name} -> {d.name}")
        sys.exit(1)

    verb = "Renamed" if apply else "Would rename"
    for src, dst in renames:
        if apply:
            src.rename(dst)
    print(f"{verb} {len(renames)} files (dropped trailing -<nid>).")
    print(f"Kept the -<nid> suffix on {sum(len(f) for _, f in collisions)} files in "
          f"{len(collisions)} slug-collision group(s):")
    for slug, members in collisions:
        print(f"  {slug}  <- {members}")
    if not apply:
        for src, dst in renames[:8]:
            print(f"    e.g. {src.name} -> {dst.name}")
        if len(renames) > 8:
            print(f"    ... and {len(renames) - 8} more")
        print("\nDry run — no files renamed. Use --apply.")


def main():
    parser = argparse.ArgumentParser(description="Drop -{drupal_nid} from content slugs (idempotent).")
    parser.add_argument("--apply", action="store_true", help="Actually rename (default is a dry run).")
    args = parser.parse_args()
    run(apply=args.apply)


if __name__ == "__main__":
    main()
