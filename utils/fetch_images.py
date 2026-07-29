#!/usr/bin/env python3
"""
Fetch images referenced by Hugo content from the old Drupal site.

Two sources of image references:
  1. Inline markdown images  — ![alt](/sites/default/files/foo.jpg)
  2. Frontmatter file IDs    — splash_image_fid / thumbnail_fid

For (2), the file_managed table in the SQL dump maps fid → public:// URI,
which translates to https://teachinghistory.org/sites/default/files/...

Downloads are saved under  static/files/  preserving the subdirectory
structure so Hugo can serve them at  /files/...

After downloading, inline markdown image paths are rewritten in-place to
point to the new local /files/ location.

Usage:
    python fetch_images.py --sql ../utils/th_db.sql \
        --content ../teachinghistory-website/content \
        --static ../teachinghistory-website/static \
        --rewrite

    python fetch_images.py --sql ../utils/th_db.sql \
        --content ../teachinghistory-website/content \
        --static ../teachinghistory-website/static \
        --dry-run
"""

import argparse
import re
import sys
import time
import urllib.parse
from pathlib import Path
from collections import defaultdict

try:
    import requests
    import yaml
except ImportError:
    print("Please install required packages:")
    print("  uv pip install requests pyyaml")
    sys.exit(1)


SITE_BASE = "https://teachinghistory.org"

# Frontmatter keys that contain Drupal file IDs
FID_KEYS = ("splash_image_fid", "thumbnail_fid", "image_fid", "author_image_fid")

# Image extensions we care about
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp", ".ico"}


# ── SQL parsing ─────────────────────────────────────────────────────────

def parse_file_managed(sql_path):
    """Parse file_managed INSERT statements from the SQL dump.

    Returns dict mapping int(fid) → relative path (e.g. 'lesson_image/TRPainting_0.jpg').
    """
    fid_map = {}
    in_file_managed = False
    buffer = ""

    with open(sql_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "INSERT INTO `file_managed`" in line:
                in_file_managed = True
                buffer = line
                continue

            if in_file_managed:
                buffer += line
                if line.rstrip().endswith(";"):
                    _parse_fm_insert(buffer, fid_map)
                    in_file_managed = False
                    buffer = ""

    return fid_map


def _parse_fm_insert(sql_text, fid_map):
    """Extract (fid, uri) from a bulk INSERT INTO file_managed VALUES (...) statement."""
    # Match individual row tuples
    row_re = re.compile(r"\((\d+),\s*\d+,\s*'(?:[^'\\]|\\.)*',\s*'((?:[^'\\]|\\.)*)'")
    for m in row_re.finditer(sql_text):
        fid = int(m.group(1))
        uri = m.group(2).replace("\\'", "'").replace("\\\\", "\\")

        # Convert public://foo/bar.jpg  →  foo/bar.jpg
        if uri.startswith("public://"):
            rel_path = uri[len("public://"):]
        else:
            rel_path = uri

        fid_map[fid] = rel_path

    return fid_map


# ── Content scanning ────────────────────────────────────────────────────

def parse_frontmatter(text):
    """Split Hugo markdown into (frontmatter_dict, body_str)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    fm_text = text[3:end].strip()
    body = text[end + 3:]
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, body


# Regex for markdown images: ![alt](url)
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")


def scan_content(content_dir):
    """Scan all .md files for image references.

    Returns:
        fid_refs:    dict[fid_int] → set of (file_path, key_name)
        inline_refs: dict[url_string] → set of file_paths
    """
    fid_refs = defaultdict(set)      # fid → {(path, key), ...}
    inline_refs = defaultdict(set)   # url → {path, ...}

    content_path = Path(content_dir)
    for md_file in content_path.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        fm, body = parse_frontmatter(text)

        # Frontmatter fid references
        for key in FID_KEYS:
            val = fm.get(key)
            if val is not None:
                try:
                    fid_refs[int(val)].add((str(md_file), key))
                except (ValueError, TypeError):
                    pass

        # Inline markdown images
        for m in MD_IMAGE_RE.finditer(body):
            url = m.group(1)
            # Skip external images (Creative Commons badges, etc.)
            if url.startswith("http") and "teachinghistory.org" not in url:
                continue
            inline_refs[url].add(str(md_file))

    return fid_refs, inline_refs


# ── URL normalization ───────────────────────────────────────────────────

def normalize_url(url):
    """Normalize various Drupal image URL patterns to a consistent form.

    Returns (download_url, local_rel_path) or (None, None) if not an image.
    """
    # Strip leading/trailing whitespace
    url = url.strip()

    # Absolute teachinghistory.org URLs
    if url.startswith("http://teachinghistory.org/") or url.startswith("https://teachinghistory.org/"):
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
    elif url.startswith("http"):
        # External URL, skip
        return None, None
    else:
        path = url

    # Normalize the path
    # /sites/default/files/foo.jpg  →  files/foo.jpg
    # /files/foo.jpg                →  files/foo.jpg
    # /sites/all/themes/...         →  skip (theme assets)
    if "/sites/all/themes/" in path:
        return None, None

    if path.startswith("/sites/default/files/"):
        rel = path[len("/sites/default/files/"):]
    elif path.startswith("/files/"):
        rel = path[len("/files/"):]
    elif path.startswith("/system/files/"):
        rel = path[len("/system/files/"):]
    else:
        # Unknown path pattern; try downloading from the path as-is
        rel = path.lstrip("/")

    # URL-decode the path
    rel = urllib.parse.unquote(rel)

    download_url = f"{SITE_BASE}/sites/default/files/{urllib.parse.quote(rel, safe='/')}"
    local_rel = rel

    return download_url, local_rel


# ── Downloading ─────────────────────────────────────────────────────────

def download_image(url, dest_path, session, dry_run=False):
    """Download a single image. Returns (success, status_code_or_error)."""
    if dest_path.exists():
        return "exists", 0

    if dry_run:
        return "would_download", 0

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        resp = session.get(url, timeout=30, allow_redirects=True)
        if resp.status_code == 200:
            dest_path.write_bytes(resp.content)
            return "downloaded", resp.status_code
        else:
            return "http_error", resp.status_code
    except Exception as e:
        return "error", str(e)


# ── Path rewriting ──────────────────────────────────────────────────────

def rewrite_inline_paths(inline_refs, url_map):
    """Rewrite inline markdown image paths in content files to /files/... paths.

    url_map: dict mapping original URL → local_rel_path (under static/files/)
    """
    # Group rewrites by file
    file_rewrites = defaultdict(list)  # filepath → [(old_url, new_url), ...]

    for old_url, file_set in inline_refs.items():
        local_rel = url_map.get(old_url)
        if local_rel is None:
            continue
        new_url = f"/files/{local_rel}"
        if old_url != new_url:
            for fpath in file_set:
                file_rewrites[fpath].append((old_url, new_url))

    rewritten_count = 0
    for fpath, replacements in file_rewrites.items():
        try:
            text = Path(fpath).read_text(encoding="utf-8")
        except Exception:
            continue

        modified = text
        for old_url, new_url in replacements:
            modified = modified.replace(f"]({old_url})", f"]({new_url})")

        if modified != text:
            Path(fpath).write_text(modified, encoding="utf-8")
            rewritten_count += 1

    return rewritten_count


def rewrite_fid_frontmatter(fid_refs, fid_map):
    """Replace numeric fid values in frontmatter with /files/ paths.

    For splash_image_fid: '1234'  →  splash_image: /files/foo.jpg
    """
    files_changed = 0

    # Group by file
    file_fids = defaultdict(list)  # filepath → [(key, fid), ...]
    for fid, ref_set in fid_refs.items():
        for fpath, key in ref_set:
            file_fids[fpath].append((key, fid))

    for fpath, pairs in file_fids.items():
        try:
            text = Path(fpath).read_text(encoding="utf-8")
        except Exception:
            continue

        fm, body = parse_frontmatter(text)
        changed = False

        for key, fid in pairs:
            rel_path = fid_map.get(fid)
            if rel_path is None:
                continue

            # Add a new key without _fid suffix pointing to the local path
            new_key = key.replace("_fid", "")
            if new_key not in fm:
                fm[new_key] = f"/files/{rel_path}"
                changed = True

        if changed:
            fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False,
                               sort_keys=False)
            merged = f"---\n{fm_str}---\n{body}"
            Path(fpath).write_text(merged, encoding="utf-8")
            files_changed += 1

    return files_changed


# ── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fetch images from old Drupal site for Hugo migration")
    parser.add_argument("--sql", required=True,
                        help="Path to Drupal SQL dump (th_db.sql)")
    parser.add_argument("--content", required=True,
                        help="Path to Hugo content directory")
    parser.add_argument("--static", required=True,
                        help="Path to Hugo static directory")
    parser.add_argument("--rewrite", action="store_true",
                        help="Rewrite image paths in content files after downloading")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be downloaded without downloading")
    parser.add_argument("--delay", type=float, default=0.1,
                        help="Delay between downloads in seconds (default 0.1)")
    args = parser.parse_args()

    static_files = Path(args.static) / "files"

    # Step 1: Parse file_managed table
    print("Parsing file_managed from SQL dump...")
    fid_map = parse_file_managed(args.sql)
    print(f"  Found {len(fid_map):,} file records")

    # Step 2: Scan content for image references
    print("\nScanning content for image references...")
    fid_refs, inline_refs = scan_content(args.content)
    print(f"  Frontmatter fid refs: {len(fid_refs):,} unique fids across {sum(len(v) for v in fid_refs.values()):,} files")
    print(f"  Inline image refs:    {len(inline_refs):,} unique URLs across {sum(len(v) for v in inline_refs.values()):,} files")

    # Step 3: Build download queue
    download_queue = {}  # local_rel_path → download_url
    url_map = {}         # original_url → local_rel_path  (for rewriting)

    # From fid references
    fid_resolved = 0
    fid_missing = 0
    for fid in fid_refs:
        rel_path = fid_map.get(fid)
        if rel_path:
            fid_resolved += 1
            download_url = f"{SITE_BASE}/sites/default/files/{urllib.parse.quote(rel_path, safe='/')}"
            download_queue[rel_path] = download_url
        else:
            fid_missing += 1

    print(f"\n  FID resolution: {fid_resolved:,} resolved, {fid_missing:,} not in file_managed")

    # From inline references
    inline_resolved = 0
    inline_skipped = 0
    for url in inline_refs:
        download_url, local_rel = normalize_url(url)
        if download_url and local_rel:
            inline_resolved += 1
            download_queue[local_rel] = download_url
            url_map[url] = local_rel
        else:
            inline_skipped += 1

    print(f"  Inline resolution: {inline_resolved:,} resolved, {inline_skipped:,} skipped (external/theme)")

    # Deduplicate
    print(f"\n  Total unique files to download: {len(download_queue):,}")

    # Filter to image files only
    image_queue = {k: v for k, v in download_queue.items()
                   if Path(k).suffix.lower() in IMAGE_EXTS}
    other_queue = {k: v for k, v in download_queue.items()
                   if Path(k).suffix.lower() not in IMAGE_EXTS}

    print(f"  Image files: {len(image_queue):,}")
    print(f"  Other files (pdf, doc, etc.): {len(other_queue):,}")

    # Step 4: Download
    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{prefix}Downloading {len(image_queue):,} image files...")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "TeachingHistory-Hugo-Migration/1.0 (site rebuild; one-time fetch)"
    })

    results = defaultdict(int)
    errors = []

    for i, (rel_path, url) in enumerate(sorted(image_queue.items()), 1):
        dest = static_files / rel_path
        status, code = download_image(url, dest, session, dry_run=args.dry_run)
        results[status] += 1

        if status == "http_error":
            errors.append((rel_path, code))

        if i % 100 == 0 or i == len(image_queue):
            print(f"  [{i:,}/{len(image_queue):,}] {status}: {rel_path[:60]}")

        if status == "downloaded" and args.delay:
            time.sleep(args.delay)

    # Report
    print(f"\n{prefix}Download results:")
    print(f"  Downloaded:      {results.get('downloaded', 0):,}")
    print(f"  Already existed: {results.get('exists', 0):,}")
    print(f"  Would download:  {results.get('would_download', 0):,}")
    print(f"  HTTP errors:     {results.get('http_error', 0):,}")
    print(f"  Other errors:    {results.get('error', 0):,}")

    if errors:
        print(f"\nHTTP errors (first 20):")
        for rel_path, code in errors[:20]:
            print(f"  {code}: {rel_path}")

    # Step 5: Rewrite paths
    if args.rewrite and not args.dry_run:
        print("\nRewriting inline image paths in content files...")
        count = rewrite_inline_paths(inline_refs, url_map)
        print(f"  Rewrote paths in {count:,} files")

        print("Adding resolved image paths to frontmatter...")
        count = rewrite_fid_frontmatter(fid_refs, fid_map)
        print(f"  Updated frontmatter in {count:,} files")

    print("\nDone!")


if __name__ == "__main__":
    main()
