# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyyaml",
# ]
# ///
"""
Relocate legacy Drupal `url:` frontmatter to `aliases:` for the teachinghistory.org
Hugo site.

Part of the Caddy-redirect pipeline (see utils/redirect_mapper.py). Moving `url:`
out of the serving position makes Hugo emit NATIVE structural URLs, while the old
Drupal path is preserved as data in `aliases:`. Hugo's `disableAliases = true`
(set in hugo.toml) means Hugo writes NO redirect stub HTML — the web server (Caddy)
owns all redirects. The `aliases:` values are consumed by the Hugo redirects
manifest (layouts/index.redirects.json) to build the legacy -> native map.

This edit is a minimal, line-oriented rewrite (the whole YAML block is NOT
re-serialized, so unrelated frontmatter is left byte-for-byte unchanged) and is
idempotent: files that already have `aliases:` (and no `url:`) are skipped, so
re-running is a no-op.

Usage:
    uv run utils/relocate_urls.py            # Dry run: report what would change
    uv run utils/relocate_urls.py --apply    # Rewrite files in place
"""

import argparse
import re
import sys
from pathlib import Path

CONTENT_DIR = Path(__file__).resolve().parent.parent / "teachinghistory-website" / "content"

# Frontmatter block at the very top of the file: ---\n ... \n---\n
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# A `url:` key line inside the frontmatter (unquoted single value, as used sitewide).
URL_LINE_RE = re.compile(r"^url:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
# Presence of an existing `aliases:` key (idempotency / conflict guard).
ALIASES_KEY_RE = re.compile(r"^aliases:", re.MULTILINE)


def relocate_in_text(text: str) -> tuple[str | None, str]:
    """Return (new_text, status).

    new_text is None when nothing should change. status is one of:
      changed, no_frontmatter, no_url, has_aliases.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, "no_frontmatter"

    block = m.group(1)

    if ALIASES_KEY_RE.search(block):
        # Already migrated (or hand-authored aliases). Leave untouched.
        return None, "has_aliases"

    url_m = URL_LINE_RE.search(block)
    if not url_m:
        return None, "no_url"

    value = url_m.group(1).strip().rstrip("\r")
    new_block = block[: url_m.start()] + f"aliases:\n- {value}" + block[url_m.end():]
    new_text = text[: m.start(1)] + new_block + text[m.end(1):]
    return new_text, "changed"


def run(apply: bool):
    if not CONTENT_DIR.exists():
        print(f"Content directory not found: {CONTENT_DIR}")
        sys.exit(1)

    counts = {"changed": 0, "no_frontmatter": 0, "no_url": 0, "has_aliases": 0}
    changed_files = []

    for md_file in sorted(CONTENT_DIR.rglob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        new_text, status = relocate_in_text(text)
        counts[status] += 1
        if status == "changed":
            changed_files.append(md_file.relative_to(CONTENT_DIR))
            if apply:
                md_file.write_text(new_text, encoding="utf-8")

    verb = "Rewrote" if apply else "Would rewrite"
    print(f"{verb} {counts['changed']} files (url: -> aliases:).")
    print(f"  already have aliases: {counts['has_aliases']}")
    print(f"  no url: field:        {counts['no_url']}")
    print(f"  no frontmatter:       {counts['no_frontmatter']}")
    if not apply:
        for rel in changed_files[:10]:
            print(f"    e.g. {rel}")
        if len(changed_files) > 10:
            print(f"    ... and {len(changed_files) - 10} more")
        print("\nDry run — no files modified. Use --apply to rewrite.")


def main():
    parser = argparse.ArgumentParser(
        description="Relocate legacy `url:` frontmatter to `aliases:` (idempotent)."
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually rewrite files (default is a dry run).",
    )
    args = parser.parse_args()
    run(apply=args.apply)


if __name__ == "__main__":
    main()
