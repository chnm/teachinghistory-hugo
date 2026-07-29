#!/usr/bin/env python3
"""
Reprocess existing Hugo content files to fix issues from the initial conversion.

Fixes:
1. Paragraph breaks — inserts blank lines between consecutive text paragraphs
   that were collapsed because Drupal's filter_autop was not replicated.
2. Pull quotes — identifies pull-quote blockquotes (converted as plain > )
   and replaces them with {{< pullquote >}} Hugo shortcodes.
3. Taxonomy — extracts taxonomy data from the Drupal SQL dump and adds
   vocabulary-grouped terms to Hugo frontmatter.

Usage:
    # All fixes (requires SQL for taxonomy + pull quotes):
    python reprocess_content.py --sql th_db.sql --content ../teachinghistory-website/content

    # Paragraph fixes only (no SQL needed):
    python reprocess_content.py --fix-paragraphs --content ../teachinghistory-website/content

    # Taxonomy only:
    python reprocess_content.py --taxonomy --sql th_db.sql --content ../teachinghistory-website/content

    # Dry run (show what would change):
    python reprocess_content.py --sql th_db.sql --content ../teachinghistory-website/content --dry-run
"""

import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict

try:
    import yaml
except ImportError:
    print("Please install pyyaml: pip install pyyaml")
    sys.exit(1)

# Import SQL parsing infrastructure from the conversion script
from drupal_to_hugo import (
    parse_sql_file,
    parse_field_value,
    _extract_values,
    TAXONOMY_VOCAB_MAP,
)


# ---------------------------------------------------------------------------
# Paragraph break fix
# ---------------------------------------------------------------------------

def is_text_line(line):
    """Check if a line is regular body text (not a special Markdown element)."""
    stripped = line.strip()
    if not stripped:
        return False
    # Heading
    if stripped.startswith('#'):
        return False
    # Blockquote
    if stripped.startswith('>'):
        return False
    # Unordered list item
    if re.match(r'^[\*\-\+]\s', stripped):
        return False
    # Ordered list item
    if re.match(r'^\d+\.\s', stripped):
        return False
    # Horizontal rule
    if re.match(r'^[\-\*_]{3,}\s*$', stripped):
        return False
    # Code fence
    if stripped.startswith('```'):
        return False
    # HTML tag
    if stripped.startswith('<'):
        return False
    # Table row
    if stripped.startswith('|'):
        return False
    # Hugo shortcode
    if stripped.startswith('{{'):
        return False
    # Image
    if stripped.startswith('!['):
        return False
    return True


def fix_paragraph_breaks(body_text):
    """Insert blank lines between consecutive text paragraphs.

    In the converted markdown, paragraphs from filtered_html content
    appear on consecutive lines without blank line separators, causing
    them to render as a single block of text.
    """
    if not body_text:
        return body_text

    lines = body_text.split('\n')
    if len(lines) <= 1:
        return body_text

    result = [lines[0]]
    for i in range(1, len(lines)):
        prev = lines[i - 1]
        curr = lines[i]

        # If both lines are non-empty regular text with no blank line
        # between them, insert one
        if is_text_line(prev) and is_text_line(curr):
            result.append('')
        result.append(curr)

    return '\n'.join(result)


# ---------------------------------------------------------------------------
# Pull quote fix
# ---------------------------------------------------------------------------

def extract_pull_quotes_from_sql(sql_path):
    """Extract pull quote texts and their node IDs from the SQL dump.

    Returns dict: nid -> [list of pull quote texts]
    """
    pull_quotes = defaultdict(list)

    # Patterns to match pull quote divs in parsed body text.
    # parse_field_value() already unescapes SQL strings, so these match
    # the resulting plain HTML (no backslash-escapes).
    pq_patterns = [
        re.compile(r'<div\s+class="pull quote">(.*?)</div>', re.DOTALL),
        re.compile(r'<div\s+class=pull\s+quote>(.*?)</div>', re.DOTALL),
        re.compile(r'<div\s+class=&quot;pull quote&quot;>(.*?)</div>', re.DOTALL),
    ]

    # Scan body-related INSERT statements for pull quote divs
    # and associate them with node IDs.  Include revision tables —
    # the SQL dump stores content in both current and revision tables.
    print("Scanning SQL for pull quotes...")
    in_body_insert = False
    buffer = []
    table_name = None

    body_tables = {
        'node__body', 'node__field_body', 'node__field_page_body',
        'node__field_essay', 'node__field_html', 'node__field_answer',
        'node_revision__body', 'node_revision__field_body',
        'node_revision__field_answer',
    }

    with open(sql_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if line.startswith('INSERT INTO'):
                # Flush previous buffer
                if in_body_insert and buffer:
                    _process_pq_buffer(buffer, pq_patterns, pull_quotes)
                # Check if this is a body table
                in_body_insert = False
                for tbl in body_tables:
                    if f'`{tbl}`' in line:
                        in_body_insert = True
                        break
                buffer = [line] if in_body_insert else []
            elif in_body_insert:
                buffer.append(line)
                if line.rstrip().endswith(';'):
                    _process_pq_buffer(buffer, pq_patterns, pull_quotes)
                    in_body_insert = False
                    buffer = []

    if in_body_insert and buffer:
        _process_pq_buffer(buffer, pq_patterns, pull_quotes)

    total = sum(len(v) for v in pull_quotes.values())
    print(f"  Found {total} pull quotes across {len(pull_quotes)} nodes")
    return dict(pull_quotes)


def _process_pq_buffer(buffer, patterns, pull_quotes):
    """Process a body INSERT buffer to find pull quote divs."""
    rows = _extract_values(buffer)
    for row in rows:
        if len(row) < 7:
            continue
        try:
            nid = int(parse_field_value(row[2]))
            body = parse_field_value(row[6])
        except (ValueError, IndexError, TypeError):
            continue
        if not body:
            continue
        for pat in patterns:
            for match in pat.finditer(body):
                text = match.group(1).strip()
                # Unescape SQL escapes
                text = text.replace("\\'", "'").replace('\\"', '"')
                text = text.replace('\\n', ' ').replace('\\r', '')
                text = re.sub(r'\s+', ' ', text).strip()
                if text and text not in pull_quotes[nid]:
                    pull_quotes[nid].append(text)


def apply_pullquote_fix(body_text, pq_texts):
    """Convert matching blockquotes to pullquote shortcodes.

    The original conversion turned <div class="pull quote"> into > blockquotes.
    This function finds blockquote lines whose text matches a known pull quote
    and replaces them with the Hugo shortcode.
    """
    if not pq_texts or not body_text:
        return body_text

    lines = body_text.split('\n')
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith('> '):
            # Extract blockquote text (may span multiple > lines)
            bq_lines = [stripped[2:]]
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith('> '):
                bq_lines.append(lines[j].strip()[2:])
                j += 1
            bq_text = ' '.join(bq_lines)
            # Normalize for comparison
            bq_norm = re.sub(r'\s+', ' ', bq_text).strip()
            bq_norm = bq_norm.strip('"\'')

            matched = False
            for pq in pq_texts:
                pq_norm = re.sub(r'\s+', ' ', pq).strip()
                pq_norm = pq_norm.strip('"\'')
                # Check if the blockquote matches a pull quote
                if (pq_norm in bq_norm or bq_norm in pq_norm or
                        _fuzzy_match(bq_norm, pq_norm)):
                    result.append(f'{{{{< pullquote >}}}}{bq_text}{{{{< /pullquote >}}}}')
                    matched = True
                    i = j
                    break

            if not matched:
                result.append(line)
                i += 1
        else:
            result.append(line)
            i += 1

    return '\n'.join(result)


def _fuzzy_match(a, b):
    """Check if two strings match after stripping punctuation and lowering."""
    def normalize(s):
        s = re.sub(r'[^\w\s]', '', s.lower())
        return re.sub(r'\s+', ' ', s).strip()
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    # One contains the other, or very high overlap
    return na in nb or nb in na


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

def parse_md_file(filepath):
    """Parse a Hugo markdown file into frontmatter dict and body string."""
    text = filepath.read_text(encoding='utf-8')

    # Split frontmatter from body
    if not text.startswith('---'):
        return None, text

    end = text.find('---', 3)
    if end == -1:
        return None, text

    fm_text = text[3:end].strip()
    body = text[end + 3:].lstrip('\n')

    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return None, text

    if not isinstance(fm, dict):
        return None, text

    return fm, body


def write_md_file(filepath, frontmatter, body):
    """Write a Hugo markdown file with frontmatter and body."""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('---\n')
        yaml.dump(frontmatter, f, allow_unicode=True,
                  default_flow_style=False, sort_keys=False)
        f.write('---\n\n')
        if body:
            f.write(body)


# ---------------------------------------------------------------------------
# Main reprocessing logic
# ---------------------------------------------------------------------------

def reprocess_content(content_dir, sql_path=None,
                      fix_paragraphs=True, fix_pullquotes=True,
                      fix_taxonomy=True, dry_run=False):
    """Walk content files and apply fixes."""

    content_path = Path(content_dir)
    if not content_path.is_dir():
        print(f"Error: {content_dir} is not a directory")
        sys.exit(1)

    # Load SQL data if needed
    taxonomy_terms = {}
    taxonomy_index = {}
    pull_quotes = {}

    if sql_path and (fix_taxonomy or fix_pullquotes):
        if fix_taxonomy:
            _, _, _, taxonomy_terms, taxonomy_index = parse_sql_file(sql_path)
        if fix_pullquotes:
            pull_quotes = extract_pull_quotes_from_sql(sql_path)

    # Walk all .md files
    md_files = sorted(content_path.rglob('*.md'))
    print(f"\nProcessing {len(md_files):,} markdown files...")

    stats = {
        'total': 0,
        'paragraphs_fixed': 0,
        'pullquotes_fixed': 0,
        'taxonomy_added': 0,
        'errors': 0,
    }

    for filepath in md_files:
        stats['total'] += 1
        if stats['total'] % 1000 == 0:
            print(f"  Processed {stats['total']:,} files...")

        try:
            fm, body = parse_md_file(filepath)
            if fm is None:
                continue

            nid = fm.get('drupal_nid')
            changed = False

            # Fix 1: Paragraph breaks
            if fix_paragraphs and body:
                new_body = fix_paragraph_breaks(body)
                if new_body != body:
                    body = new_body
                    changed = True
                    stats['paragraphs_fixed'] += 1

            # Fix 2: Pull quotes
            if fix_pullquotes and nid and nid in pull_quotes:
                new_body = apply_pullquote_fix(body, pull_quotes[nid])
                if new_body != body:
                    body = new_body
                    changed = True
                    stats['pullquotes_fixed'] += 1

            # Fix 3: Taxonomy
            if fix_taxonomy and nid and nid in taxonomy_index:
                node_tids = taxonomy_index[nid]
                vocab_groups = defaultdict(list)
                for tid in node_tids:
                    term = taxonomy_terms.get(tid)
                    if term:
                        vocab_groups[term['vid']].append(term['name'])

                for vid, fm_key in TAXONOMY_VOCAB_MAP.items():
                    terms = vocab_groups.get(vid, [])
                    if terms:
                        new_terms = sorted(set(terms))

                        # Map individual Drupal grades (K,1-12) to grade
                        # bands (elementary, middle, high) that the
                        # grade-level templates expect.
                        if vid == 'grade_level':
                            bands = set()
                            for g in new_terms:
                                if g in ('K', '1', '2', '3', '4', '5'):
                                    bands.add('elementary')
                                elif g in ('6', '7', '8'):
                                    bands.add('middle')
                                elif g in ('9', '10', '11', '12'):
                                    bands.add('high')
                            new_terms = sorted(bands)

                        if fm.get(fm_key) != new_terms:
                            fm[fm_key] = new_terms
                            changed = True
                            stats['taxonomy_added'] += 1

            # Write changes
            if changed and not dry_run:
                write_md_file(filepath, fm, body)

        except Exception as e:
            stats['errors'] += 1
            if stats['errors'] <= 10:
                print(f"  Error processing {filepath}: {e}")

    # Report
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"\n{prefix}Reprocessing complete:")
    print(f"  Total files scanned:  {stats['total']:,}")
    print(f"  Paragraph breaks fixed: {stats['paragraphs_fixed']:,}")
    print(f"  Pull quotes converted:  {stats['pullquotes_fixed']:,}")
    print(f"  Taxonomy terms added:   {stats['taxonomy_added']:,}")
    if stats['errors']:
        print(f"  Errors: {stats['errors']:,}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Reprocess Hugo content files to fix conversion issues'
    )
    parser.add_argument(
        '--content', required=True,
        help='Path to Hugo content directory'
    )
    parser.add_argument(
        '--sql', default=None,
        help='Path to Drupal SQL dump (required for taxonomy + pull quotes)'
    )
    parser.add_argument(
        '--fix-paragraphs', action='store_true', default=False,
        help='Only fix paragraph breaks (no SQL needed)'
    )
    parser.add_argument(
        '--taxonomy', action='store_true', default=False,
        help='Only extract and add taxonomy data'
    )
    parser.add_argument(
        '--pullquotes', action='store_true', default=False,
        help='Only fix pull quotes'
    )
    parser.add_argument(
        '--dry-run', action='store_true', default=False,
        help='Show what would change without writing files'
    )
    args = parser.parse_args()

    # If no specific fix flags, do all fixes
    do_all = not (args.fix_paragraphs or args.taxonomy or args.pullquotes)

    fix_paragraphs = do_all or args.fix_paragraphs
    fix_taxonomy = do_all or args.taxonomy
    fix_pullquotes = do_all or args.pullquotes

    # Validate SQL is provided when needed
    if (fix_taxonomy or fix_pullquotes) and not args.sql:
        print("Error: --sql is required for taxonomy and pull quote fixes")
        print("Use --fix-paragraphs to fix only paragraph breaks (no SQL needed)")
        sys.exit(1)

    reprocess_content(
        content_dir=args.content,
        sql_path=args.sql,
        fix_paragraphs=fix_paragraphs,
        fix_pullquotes=fix_pullquotes,
        fix_taxonomy=fix_taxonomy,
        dry_run=args.dry_run,
    )
