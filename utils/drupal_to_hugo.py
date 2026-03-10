#!/usr/bin/env python3
"""
Convert Drupal SQL dump to Hugo markdown files.
Handles large single INSERT statements with thousands of rows.

Extracts content from multiple Drupal field tables to capture body text,
sidebar metadata, author bios, images, and other fields that were previously
missed when only node__body and node__field_body were parsed.
"""

import re
import sys
from datetime import datetime
from pathlib import Path
import unicodedata
from collections import defaultdict

try:
    from markdownify import markdownify as md
    import yaml
    from bs4 import BeautifulSoup
except ImportError:
    print("Please install required packages:")
    print("uv pip install markdownify pyyaml beautifulsoup4")
    sys.exit(1)


# ---------------------------------------------------------------------------
# All node__field_* tables we want to extract.  Each entry maps a SQL table
# name to the key used in the per-node `fields` dict.
#
# Drupal field tables share a common schema:
#   (bundle, deleted, entity_id, revision_id, langcode, delta, field_X_value, ...)
# The value column is always index 6.  Some tables have a second value
# column at index 7 (e.g. summary, format).
# ---------------------------------------------------------------------------

TEXT_FIELD_TABLES = {
    # Primary body fields
    'node__field_body':               'field_body',
    'node__field_html':               'field_html',
    'node__field_page_body':          'field_page_body',
    'node__field_essay':              'field_essay',

    # Description / abstract / overview / glance
    'node__field_description':        'field_description',
    'node__field_abstract':           'field_abstract',
    'node__field_overview':           'field_overview',
    'node__field_glance':             'field_glance',
    'node__field_executive_summary':  'field_executive_summary',

    # Teaser / learn-more / spotlight
    'node__field_teaser_text':        'field_teaser_text',
    'node__field_learn_more_text':    'field_learn_more_text',
    'node__field_spotlight_text':     'field_spotlight_text',

    # Beyond the Textbook excerpt fields
    'node__field_historian_excerpt':  'field_historian_excerpt',
    'node__field_source_excerpt':     'field_source_excerpt',
    'node__field_textbook_excerpt':   'field_textbook_excerpt',

    # Video / transcript
    'node__field_transcript_text':    'field_transcript_text',
    'node__field_video_overview':     'field_video_overview',

    # Quiz
    'node__field_quiz_instructions':  'field_quiz_instructions',
    'node__field_quiz_answer':        'field_quiz_answer',

    # Q&A
    'node__field_question':           'field_question',
    'node__field_answer':             'field_answer',

    # Teaching guide prototypes
    'node__field_instruction_text':   'field_instruction_text',
    'node__field_drop_down_intro':    'field_drop_down_intro',

    # Author
    'node__field_author_biography':   'field_author_biography',

    # Misc metadata (stored as text)
    'node__field_notes':              'field_notes',
    'node__field_bibliography':       'field_bibliography',
    'node__field_primary_annotated_biblio': 'field_primary_annotated_biblio',
    'node__field_secondary_annotated_bib':  'field_secondary_annotated_bib',
    'node__field_core_questions':     'field_core_questions',
}

# Integer / short-value fields stored in frontmatter
METADATA_FIELD_TABLES = {
    'node__field_flexibility_scale':  'flexibility_scale',
    'node__field_duration':           'duration',
    'node__field_grade_tested':       'grade_tested',
    'node__field_topic':              'topic',
    'node__field_keywords':           'keywords',
    'node__field_quiz_id':            'quiz_id',
    'node__field_website':            'website_url',
    'node__field_date_published':     'date_published',
    'node__field_target_audience':    'target_audience',
    'node__field_thinking_focus':     'thinking_focus',
    'node__field_series_name':        'series_name',
}

# Image fields — value is a Drupal file entity ID (integer)
IMAGE_FIELD_TABLES = {
    'node__field_image':              'image_fid',
    'node__field_splash_image':       'splash_image_fid',
    'node__field_thumbnail':          'thumbnail_fid',
    'node__field_author_image':       'author_image_fid',
}

# Combine all tracked tables for detection
ALL_FIELD_TABLES = set(TEXT_FIELD_TABLES) | set(METADATA_FIELD_TABLES) | set(IMAGE_FIELD_TABLES)


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    if not text:
        return ""
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^\w\s-]', '', text.lower())
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')[:100]


def extract_row_tuples(values_text):
    """Extract individual row tuples from VALUES clause."""
    rows = []
    current_row = []
    current_field = []
    depth = 0
    in_string = False
    escape_next = False
    i = 0

    while i < len(values_text):
        char = values_text[i]

        if escape_next:
            current_field.append(char)
            escape_next = False
            i += 1
            continue

        if char == '\\' and in_string:
            if i + 1 < len(values_text):
                next_char = values_text[i + 1]
                if next_char in ["'", '"', '\\', 'n', 'r', 't', '0']:
                    escape_next = True
                    current_field.append(char)
                    i += 1
                    continue
            current_field.append(char)
            i += 1
            continue

        if char == "'":
            if not in_string:
                in_string = True
            else:
                if i + 1 < len(values_text) and values_text[i + 1] == "'":
                    current_field.append("'")
                    i += 2
                    continue
                in_string = False
            i += 1
            continue

        if not in_string:
            if char == '(':
                depth += 1
                if depth == 1:
                    current_row = []
                    current_field = []
                i += 1
                continue
            elif char == ')':
                depth -= 1
                if depth == 0:
                    if current_field or (not current_field and current_row):
                        field_val = ''.join(current_field).strip()
                        current_row.append(field_val)
                    if current_row:
                        rows.append(current_row)
                    current_row = []
                    current_field = []
                i += 1
                continue
            elif char == ',' and depth == 1:
                field_val = ''.join(current_field).strip()
                current_row.append(field_val)
                current_field = []
                i += 1
                continue
            elif char in [' ', '\n', '\r', '\t'] and depth == 0:
                i += 1
                continue

        current_field.append(char)
        i += 1

    return rows


def parse_field_value(val):
    """Parse a field value from SQL."""
    val = val.strip()
    if val == 'NULL' or val == '':
        return None

    val = val.replace('\\\\', '\x00')
    val = val.replace("\\'", "'")
    val = val.replace('\\"', '"')
    val = val.replace('\\n', '\n')
    val = val.replace('\\r', '\r')
    val = val.replace('\\t', '\t')
    val = val.replace('\\0', '')
    val = val.replace('\x00', '\\')

    return val


def _extract_values(lines):
    """Join buffer lines and extract VALUES rows."""
    full_text = ''.join(lines)
    match = re.search(r'VALUES\s+(.+);?\s*$', full_text, re.DOTALL)
    if not match:
        return []
    return extract_row_tuples(match.group(1).rstrip(';'))


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_node_insert(lines, nodes):
    """Parse node_field_data INSERT statement."""
    rows = _extract_values(lines)
    for row in rows:
        if len(row) >= 9:
            try:
                nid = int(parse_field_value(row[0]))
                nodes[nid] = {
                    'nid': nid,
                    'type': parse_field_value(row[2]),
                    'status': parse_field_value(row[4]) == '1',
                    'title': parse_field_value(row[5]),
                    'created': int(parse_field_value(row[7])),
                    'changed': int(parse_field_value(row[8])),
                    'promote': parse_field_value(row[9]) == '1' if len(row) > 9 else False,
                    'sticky': parse_field_value(row[10]) == '1' if len(row) > 10 else False,
                }
            except (ValueError, IndexError, TypeError):
                pass


def parse_body_insert(lines, fields):
    """Parse node__body INSERT (bio/description + summary)."""
    rows = _extract_values(lines)
    print(f"    Found {len(rows)} body rows")
    for row in rows:
        if len(row) >= 7:
            try:
                nid = int(parse_field_value(row[2]))
                if nid not in fields:
                    fields[nid] = {}
                fields[nid]['body'] = parse_field_value(row[6])
                if len(row) > 7:
                    summary = parse_field_value(row[7])
                    if summary:
                        fields[nid]['body_summary'] = summary
            except (ValueError, IndexError, TypeError):
                continue


def parse_text_field_insert(lines, fields, field_key):
    """Generic parser for any text field table.

    Drupal field tables have a common schema:
      (bundle, deleted, entity_id, revision_id, langcode, delta, value, [format])
    We extract entity_id (index 2) and value (index 6).
    """
    rows = _extract_values(lines)
    print(f"    Found {len(rows)} {field_key} rows")
    for row in rows:
        if len(row) >= 7:
            try:
                nid = int(parse_field_value(row[2]))
                val = parse_field_value(row[6])
                if val:
                    if nid not in fields:
                        fields[nid] = {}
                    # Some fields can have multiple deltas (e.g. images).
                    # For text fields we take the first (delta=0) or concatenate.
                    existing = fields[nid].get(field_key)
                    if existing:
                        fields[nid][field_key] = existing + '\n\n' + val
                    else:
                        fields[nid][field_key] = val
            except (ValueError, IndexError, TypeError):
                continue


def parse_path_alias_insert(lines, paths):
    """Parse path_alias INSERT statement for URLs."""
    rows = _extract_values(lines)
    print(f"    Found {len(rows)} path alias rows")
    for row in rows:
        if len(row) >= 6:
            try:
                path = parse_field_value(row[4])
                alias = parse_field_value(row[5])
                if path and path.startswith('/node/'):
                    nid = int(path.replace('/node/', ''))
                    if alias:
                        paths[nid] = alias
            except (ValueError, IndexError, TypeError):
                continue


# ---------------------------------------------------------------------------
# SQL file scanner
# ---------------------------------------------------------------------------

def _detect_table(line):
    """Detect which tracked table an INSERT INTO line targets.

    Returns a (category, table_name) tuple or None.
    Categories: 'nodes', 'body', 'path', 'text_field', 'meta_field', 'image_field'
    """
    if not line.startswith('INSERT INTO'):
        return None

    if 'node_field_data' in line:
        return ('nodes', 'node_field_data')

    # node__body but NOT node__field_body
    if '`node__body`' in line:
        return ('body', 'node__body')

    if 'path_alias' in line and 'migrate' not in line:
        return ('path', 'path_alias')

    # Check all tracked field tables
    for table_name in ALL_FIELD_TABLES:
        # Use backtick-wrapped name for exact match
        if f'`{table_name}`' in line:
            if table_name in TEXT_FIELD_TABLES:
                return ('text_field', table_name)
            elif table_name in METADATA_FIELD_TABLES:
                return ('meta_field', table_name)
            elif table_name in IMAGE_FIELD_TABLES:
                return ('image_field', table_name)

    return None


def _flush_buffer(category, table_name, buffer, nodes, fields, paths):
    """Process a completed INSERT buffer."""
    if not buffer:
        return

    label = table_name.replace('node__', '')
    print(f"  Parsing {len(buffer)} lines of {label} data...")

    if category == 'nodes':
        parse_node_insert(buffer, nodes)
    elif category == 'body':
        parse_body_insert(buffer, fields)
    elif category == 'path':
        parse_path_alias_insert(buffer, paths)
    elif category == 'text_field':
        field_key = TEXT_FIELD_TABLES[table_name]
        parse_text_field_insert(buffer, fields, field_key)
    elif category in ('meta_field', 'image_field'):
        mapping = METADATA_FIELD_TABLES if category == 'meta_field' else IMAGE_FIELD_TABLES
        field_key = mapping[table_name]
        parse_text_field_insert(buffer, fields, field_key)


def parse_sql_file(sql_path):
    """Parse SQL file and extract node data, fields, and paths."""

    print(f"Parsing {sql_path}...")
    print("This may take several minutes...")

    nodes = {}
    fields = {}  # nid -> {field_key: value, ...}
    paths = {}

    current_category = None
    current_table = None
    buffer = []
    line_count = 0

    with open(sql_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line_count += 1
            if line_count % 100000 == 0:
                print(f"  Processed {line_count:,} lines...")

            detected = _detect_table(line) if line.startswith('INSERT') else None

            if detected:
                # Flush previous buffer
                if current_table and buffer:
                    _flush_buffer(current_category, current_table, buffer,
                                  nodes, fields, paths)

                current_category, current_table = detected
                buffer = [line]

            elif current_table:
                buffer.append(line)

                # Check if INSERT is complete
                if line.rstrip().endswith(';'):
                    _flush_buffer(current_category, current_table, buffer,
                                  nodes, fields, paths)
                    current_table = None
                    current_category = None
                    buffer = []

    # Flush any remaining buffer
    if current_table and buffer:
        _flush_buffer(current_category, current_table, buffer,
                      nodes, fields, paths)

    # Count how many nodes have at least one field
    nodes_with_fields = sum(1 for nid in nodes if nid in fields)

    print(f"\n✓ Extracted {len(nodes):,} nodes, "
          f"{nodes_with_fields:,} with field data, "
          f"and {len(paths):,} URL paths")
    return nodes, fields, paths


# ---------------------------------------------------------------------------
# HTML preprocessing & Markdown conversion
# ---------------------------------------------------------------------------

def preprocess_html(html_content):
    """Preprocess HTML to convert custom Drupal elements to standard HTML."""
    if not html_content:
        return html_content

    try:
        soup = BeautifulSoup(html_content, 'html.parser')

        for div in soup.find_all('div', class_='subhead'):
            h2 = soup.new_tag('h2')
            h2.string = div.get_text()
            div.replace_with(h2)

        for div in soup.find_all('div', class_='pull'):
            blockquote = soup.new_tag('blockquote')
            blockquote.string = div.get_text()
            div.replace_with(blockquote)

        if soup.body:
            return ''.join(str(tag) for tag in soup.body.children)
        else:
            return str(soup)
    except Exception:
        return html_content


def html_to_md(html):
    """Convert HTML string to Markdown, returning empty string for None/empty."""
    if not html:
        return ''
    html = preprocess_html(html)
    try:
        return md(html, heading_style="ATX")
    except Exception:
        return html


# ---------------------------------------------------------------------------
# Body composition — picks the right fields for each content type
# ---------------------------------------------------------------------------

# Priority-ordered list of field keys to try for the main body content
# per content type.  First non-empty match wins.
BODY_FIELD_PRIORITY = {
    'beyond_the_chalkboard': [
        'field_html', 'field_transcript_text', 'field_body',
        'field_learn_more_text',
    ],
    'beyond_the_textbook': [
        'field_body',  # part-2 had field_body
    ],
    'research_tool': [
        'field_glance', 'field_learn_more_text', 'field_body',
    ],
    'website': [
        'field_abstract', 'field_teaser_text', 'field_body',
    ],
    'english_language_learners': [
        'field_body', 'field_learn_more_text',
    ],
    'ex_of_historical_thinking': [
        'field_html', 'field_transcript_text', 'field_body',
        'field_video_overview',
    ],
    'examples_of_teaching': [
        'field_html', 'field_transcript_text', 'field_body',
        'field_video_overview',
    ],
    'quizly': [
        'field_quiz_instructions', 'field_body',
    ],
    'quiz': [
        'field_quiz_instructions', 'field_quiz_answer', 'field_body',
    ],
    'historical_site': [
        'field_description', 'field_body',
    ],
    'history_in_multimedia': [
        'field_description', 'field_body',
    ],
    'tah_grant': [
        'field_abstract', 'field_body',
    ],
    'press_release': [
        'field_body', 'body',
    ],
    'teaching_guides_prototype_gen': [
        'field_instruction_text', 'field_body',
    ],
    'teaching_guides_prototype_gen_ch': [
        'field_page_body', 'field_body',
    ],
    'teaching_guides_prototype_child': [
        'field_essay', 'field_body',
    ],
    'teaching_guides_prototype': [
        'field_drop_down_intro', 'field_body',
    ],
    'research_brief': [
        'field_executive_summary', 'field_body',
    ],
    'lessons_learned': [
        'field_body', 'field_transcript_text', 'field_video_overview',
    ],
}

# Default fallback order for types not listed above
DEFAULT_BODY_PRIORITY = [
    'field_body', 'body', 'field_html', 'field_description',
    'field_abstract', 'field_overview', 'field_glance',
    'field_page_body', 'field_essay', 'field_executive_summary',
    'field_learn_more_text', 'field_transcript_text',
    'field_quiz_instructions', 'field_answer',
]

# Fields that should be appended as extra sections below the main body
SUPPLEMENTAL_FIELDS = {
    'beyond_the_textbook': [
        ('field_textbook_excerpt', 'What Textbooks Say'),
        ('field_historian_excerpt', 'What Historians Say'),
        ('field_source_excerpt', 'What Sources Say'),
    ],
}

# Fields that go into frontmatter as structured metadata
FRONTMATTER_FIELDS = [
    'body_summary', 'field_author_biography', 'field_question',
    'flexibility_scale', 'duration', 'grade_tested', 'topic',
    'keywords', 'quiz_id', 'website_url', 'date_published',
    'target_audience', 'thinking_focus', 'series_name',
    'image_fid', 'splash_image_fid', 'thumbnail_fid', 'author_image_fid',
    'field_teaser_text', 'field_spotlight_text',
    'field_notes', 'field_bibliography',
    'field_primary_annotated_biblio', 'field_secondary_annotated_bib',
    'field_core_questions',
]


def compose_body(content_type, field_data):
    """Build the main Markdown body from available fields.

    Returns (body_md, extra_frontmatter_dict).
    """
    priority = BODY_FIELD_PRIORITY.get(content_type, DEFAULT_BODY_PRIORITY)

    # Find primary body content
    body_html = ''
    used_key = None
    for key in priority:
        val = field_data.get(key)
        if val:
            body_html = val
            used_key = key
            break

    # For Q&A types, handle question + answer
    question = field_data.get('field_question', '')
    answer = field_data.get('field_answer', '')

    body_md = html_to_md(body_html)

    # If we have an answer and no body, use answer as body
    if answer and not body_md:
        body_md = html_to_md(answer)
    elif answer and body_md:
        answer_md = html_to_md(answer)
        body_md = f"{answer_md}\n\n---\n\n{body_md}"

    # Append supplemental sections (e.g. Beyond the Textbook excerpts)
    supplements = SUPPLEMENTAL_FIELDS.get(content_type, [])
    for field_key, heading in supplements:
        val = field_data.get(field_key)
        if val:
            section_md = html_to_md(val)
            if section_md:
                body_md = body_md + f"\n\n## {heading}\n\n{section_md}"

    # If still no body, try concatenating any remaining text fields
    if not body_md:
        for key in DEFAULT_BODY_PRIORITY:
            val = field_data.get(key)
            if val:
                body_md = html_to_md(val)
                break

    # Build extra frontmatter from metadata fields
    extra_fm = {}

    summary = field_data.get('body_summary', '')
    if summary:
        extra_fm['summary'] = html_to_md(summary).strip()

    bio = field_data.get('field_author_biography', '') or field_data.get('body', '')
    # Only use 'body' as bio if we used a different field for main content
    if not bio and used_key != 'body':
        bio = field_data.get('body', '')
    elif used_key == 'body':
        bio = field_data.get('field_author_biography', '')
    if bio:
        bio_md = html_to_md(bio).strip()
        if bio_md:
            extra_fm['author_bio'] = bio_md

    if question:
        extra_fm['question'] = html_to_md(question).strip()

    # Structured metadata
    for key in ['flexibility_scale', 'duration', 'grade_tested', 'topic',
                'keywords', 'quiz_id', 'website_url', 'date_published',
                'target_audience', 'thinking_focus', 'series_name',
                'image_fid', 'splash_image_fid', 'thumbnail_fid',
                'author_image_fid']:
        val = field_data.get(key)
        if val:
            extra_fm[key] = val.strip() if isinstance(val, str) else val

    # Teaser as summary fallback
    if 'summary' not in extra_fm:
        teaser = field_data.get('field_teaser_text', '')
        if teaser:
            extra_fm['summary'] = html_to_md(teaser).strip()

    # Spotlight text
    spotlight = field_data.get('field_spotlight_text', '')
    if spotlight:
        extra_fm['spotlight'] = html_to_md(spotlight).strip()

    return body_md, extra_fm


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_to_hugo(nodes, fields, paths, output_dir="content"):
    """Export parsed data to Hugo markdown files."""

    print(f"\nCreating Hugo markdown files...")

    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    stats = defaultdict(int)
    body_stats = defaultdict(int)
    processed = 0

    for nid, node in nodes.items():
        if not node['status']:
            continue

        content_type = node['type']
        if not content_type:
            continue

        type_dir = output_path / content_type.replace('_', '-')
        type_dir.mkdir(exist_ok=True)

        stats[content_type] += 1

        field_data = fields.get(nid, {})
        body_md, extra_fm = compose_body(content_type, field_data)

        if body_md.strip():
            body_stats[content_type] += 1

        # Build frontmatter
        try:
            created_date = datetime.fromtimestamp(node['created'])
            updated_date = datetime.fromtimestamp(node['changed'])
        except Exception:
            created_date = datetime.now()
            updated_date = datetime.now()

        frontmatter = {
            'title': node['title'] or f"Node {nid}",
            'date': created_date.isoformat(),
            'lastmod': updated_date.isoformat(),
            'type': content_type,
            'draft': False,
            'drupal_nid': nid,
        }

        # Merge extra frontmatter
        for key, val in extra_fm.items():
            if val:
                frontmatter[key] = val

        if nid in paths:
            frontmatter['url'] = paths[nid]

        if node.get('promote'):
            frontmatter['featured'] = True
        if node.get('sticky'):
            frontmatter['pinned'] = True

        # Write file
        slug = slugify(node['title'])
        if not slug:
            slug = f"node-{nid}"
        filename = f"{slug}-{nid}.md"
        filepath = type_dir / filename

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('---\n')
                yaml.dump(frontmatter, f, allow_unicode=True,
                         default_flow_style=False, sort_keys=False)
                f.write('---\n\n')
                if body_md:
                    f.write(body_md)

            processed += 1
            if processed % 500 == 0:
                print(f"  Created {processed:,} files...")

        except Exception as e:
            print(f"  Error writing {filepath}: {e}")

    # Statistics
    print(f"\n✓ Created {processed:,} markdown files")

    total_with_body = sum(body_stats.values())
    print(f"  - {total_with_body:,} with body content")

    print("\nContent by type (files / with body):")
    for content_type, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
        bodies = body_stats.get(content_type, 0)
        pct = (bodies / count * 100) if count else 0
        flag = " ⚠" if pct < 50 and count > 5 else ""
        print(f"  {content_type:40s}: {count:5,} files, {bodies:5,} with body ({pct:4.0f}%){flag}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Convert Drupal SQL dump to Hugo markdown')
    parser.add_argument('--sql', default='th_db.sql', help='Path to SQL dump file')
    parser.add_argument('--output', default='content', help='Output directory for Hugo content')

    args = parser.parse_args()

    nodes, fields, paths = parse_sql_file(args.sql)
    export_to_hugo(nodes, fields, paths, args.output)

    print(f"\n✓ Conversion complete! Files written to {args.output}/")
