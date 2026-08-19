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
import csv
import re
import sys
import time
import urllib.parse
import unicodedata
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

# Frontmatter keys used by Hugo templates, in display priority order.
IMAGE_KEYS = ("splash_image", "image", "thumbnail")


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
    match = re.match(
        r"\A---[ \t]*\r?\n(?P<yaml>.*?)(?:\r?\n)---[ \t]*(?:\r?\n|\Z)",
        text,
        flags=re.DOTALL,
    )
    if not match:
        return {}, text
    fm_text = match.group('yaml').strip()
    body = text[match.end():]
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, body


# Markdown images. The legacy conversion created some unescaped destinations
# containing spaces, so accept both valid angle-bracket destinations and the
# malformed-but-recoverable form through the closing parenthesis.
MD_IMAGE_RE = re.compile(
    r"!\[[^\]]*\]\(\s*"
    r"(?:<(?P<angle>[^>]+)>|(?P<plain>[^)\n]*?))"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)"
)


def markdown_image_url(match):
    """Return the destination captured by ``MD_IMAGE_RE``."""
    return (match.group('angle') or match.group('plain') or '').strip()


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
            url = markdown_image_url(m)
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
        # Parse local URLs too so cache-busting query strings do not become
        # part of the downloaded filename.
        path = urllib.parse.urlparse(url).path

    # Normalize the path
    # /sites/default/files/foo.jpg  →  files/foo.jpg
    # /files/foo.jpg                →  files/foo.jpg
    # /sites/all/themes/...         →  skip (theme assets)
    if "/sites/all/themes/" in path:
        return None, None

    if path.startswith("/sites/default/files/"):
        rel = path[len("/sites/default/files/"):]
    elif path.startswith("/files//files/"):
        rel = path[len("/files//files/"):]
    elif path.startswith("/files/"):
        rel = path[len("/files/"):]
    elif path.startswith("/system/files/"):
        rel = path[len("/system/files/"):]
    else:
        # Unknown path pattern; try downloading from the path as-is
        rel = path.lstrip("/")

    # URL-decode the path
    rel = urllib.parse.unquote(rel).lstrip('/')
    # Repair cache-busting queries that an older rewrite encoded as part of
    # the path (for example image.jpg%3F1301077376).
    rel = re.sub(r'\?\d+$', '', rel)

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
        new_url = f"/files/{urllib.parse.quote(local_rel, safe='/')}"
        if old_url != new_url:
            for fpath in file_set:
                file_rewrites[fpath].append((old_url, local_rel))

    rewritten_count = 0
    for fpath, replacements in file_rewrites.items():
        try:
            text = Path(fpath).read_text(encoding="utf-8")
        except Exception:
            continue

        replacements_by_url = dict(replacements)

        def replace_destination(match):
            old_url = markdown_image_url(match)
            local_rel = replacements_by_url.get(old_url)
            if local_rel is None:
                return match.group(0)
            new_url = f"/files/{urllib.parse.quote(local_rel, safe='/')}"
            return match.group(0).replace(old_url, new_url, 1)

        modified = MD_IMAGE_RE.sub(replace_destination, text)

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


# ── Auditing ────────────────────────────────────────────────────────────

def _normalized_path(value):
    return unicodedata.normalize('NFC', value).casefold()


def _local_static_path(url, static_dir):
    """Resolve a local image URL under ``static_dir`` or return ``None``."""
    if not url or url.startswith(('http://', 'https://', '//', 'data:')):
        return None
    parsed = urllib.parse.urlparse(url)
    path = urllib.parse.unquote(parsed.path).lstrip('/')
    return Path(static_dir) / path


def _asset_status(url, static_dir, case_index):
    """Return ``(status, resolved_path)`` for an image URL."""
    local_path = _local_static_path(url, static_dir)
    if local_path is None:
        return 'external', ''
    relative = str(local_path.relative_to(static_dir))
    case_match = case_index.get(_normalized_path(relative))
    # Case-insensitive development filesystems can report a path as existing
    # even when its spelling would fail on the Linux deployment filesystem.
    if local_path.is_file():
        if case_match and relative != case_match:
            return 'case_mismatch', str(Path(static_dir) / case_match)
        return 'ok', str(local_path)

    if case_match:
        return 'case_mismatch', str(Path(static_dir) / case_match)
    return 'missing', str(local_path)


def audit_content_images(content_dir, static_dir, fid_map=None):
    """Audit card, author, and inline image references across Hugo content.

    The returned rows include every page that will use the card fallback plus
    every explicit image reference. This makes the report both a broken-asset
    audit and a review queue for genuinely image-less pages.
    """
    fid_map = fid_map or {}
    static_dir = Path(static_dir)
    case_index = {
        _normalized_path(str(path.relative_to(static_dir))):
            str(path.relative_to(static_dir))
        for path in static_dir.rglob('*') if path.is_file()
    }
    rows = []

    for md_file in sorted(Path(content_dir).rglob('*.md')):
        try:
            text = md_file.read_text(encoding='utf-8')
        except OSError:
            continue
        frontmatter, body = parse_frontmatter(text)
        if not frontmatter or md_file.name == '_index.md':
            continue

        common = {
            'page': str(md_file),
            'drupal_nid': frontmatter.get('drupal_nid', ''),
            'title': frontmatter.get('title', ''),
        }

        card_key = next((key for key in IMAGE_KEYS if frontmatter.get(key)), '')
        card_url = frontmatter.get(card_key, '') if card_key else ''
        if not card_url:
            for key in IMAGE_KEYS:
                fid = frontmatter.get(f'{key}_fid')
                try:
                    relative = fid_map.get(int(fid))
                except (TypeError, ValueError):
                    relative = None
                if relative:
                    card_key = f'{key}_fid'
                    card_url = f"/files/{urllib.parse.quote(relative, safe='/')}"
                    break

        if card_url:
            status, resolved = _asset_status(card_url, static_dir, case_index)
            if status == 'missing' and card_key in IMAGE_KEYS:
                fid = frontmatter.get(f'{card_key}_fid')
                try:
                    fid_relative = fid_map.get(int(fid))
                except (TypeError, ValueError):
                    fid_relative = None
                if fid_relative:
                    fid_url = (
                        f"/files/{urllib.parse.quote(fid_relative, safe='/')}"
                    )
                    fid_status, fid_path = _asset_status(
                        fid_url, static_dir, case_index
                    )
                    if fid_status in {'ok', 'case_mismatch'}:
                        status, resolved = 'fid_recoverable', fid_path
            rows.append({**common, 'usage': 'card', 'field': card_key,
                         'source': card_url, 'status': status,
                         'resolved_path': resolved})
        else:
            rows.append({**common, 'usage': 'card', 'field': '', 'source': '',
                         'status': 'fallback_no_image', 'resolved_path': ''})

        author_url = frontmatter.get('author_image')
        if author_url:
            status, resolved = _asset_status(author_url, static_dir, case_index)
            if status == 'missing':
                fid = frontmatter.get('author_image_fid')
                try:
                    fid_relative = fid_map.get(int(fid))
                except (TypeError, ValueError):
                    fid_relative = None
                if fid_relative:
                    fid_url = (
                        f"/files/{urllib.parse.quote(fid_relative, safe='/')}"
                    )
                    fid_status, fid_path = _asset_status(
                        fid_url, static_dir, case_index
                    )
                    if fid_status in {'ok', 'case_mismatch'}:
                        status, resolved = 'fid_recoverable', fid_path
            rows.append({**common, 'usage': 'author', 'field': 'author_image',
                         'source': author_url, 'status': status,
                         'resolved_path': resolved})

        for match in MD_IMAGE_RE.finditer(body):
            url = markdown_image_url(match)
            status, resolved = _asset_status(url, static_dir, case_index)
            rows.append({**common, 'usage': 'inline', 'field': 'body',
                         'source': url, 'status': status,
                         'resolved_path': resolved})

    return rows


def write_audit_report(rows, report_path):
    """Write image audit rows as CSV and return per-status counts."""
    fieldnames = [
        'page', 'drupal_nid', 'title', 'usage', 'field', 'source', 'status',
        'resolved_path',
    ]
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    counts = defaultdict(int)
    for row in rows:
        counts[row['status']] += 1
    return dict(counts)


def rewrite_audit_paths(rows, static_dir):
    """Rewrite audit-confirmed case mismatches and recoverable FID paths."""
    static_dir = Path(static_dir)
    by_page = defaultdict(dict)
    for row in rows:
        if (row.get('status') not in {'case_mismatch', 'fid_recoverable'}
                or not row.get('source')):
            continue
        resolved = Path(row['resolved_path'])
        try:
            relative = resolved.relative_to(static_dir)
        except ValueError:
            continue
        corrected = '/' + urllib.parse.quote(str(relative), safe='/')
        by_page[row['page']][row['source']] = corrected

    changed = 0
    for page, replacements in by_page.items():
        path = Path(page)
        text = path.read_text(encoding='utf-8')
        updated = text
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        if updated != text:
            path.write_text(updated, encoding='utf-8')
            changed += 1
    return changed


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
    parser.add_argument("--audit-report",
                        help="Write a CSV audit of card, author, and inline images")
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

    if args.audit_report:
        print(f"\nWriting image audit to {args.audit_report}...")
        rows = audit_content_images(args.content, args.static, fid_map)
        if args.rewrite and not args.dry_run:
            count = rewrite_audit_paths(rows, args.static)
            print(f"  Corrected audited paths in {count:,} files")
            if count:
                rows = audit_content_images(args.content, args.static, fid_map)
        counts = write_audit_report(rows, args.audit_report)
        for status, count in sorted(counts.items()):
            print(f"  {status}: {count:,}")

    print("\nDone!")


if __name__ == "__main__":
    main()
