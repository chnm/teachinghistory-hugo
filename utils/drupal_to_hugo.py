#!/usr/bin/env python3
"""
Convert Drupal SQL dump to Hugo markdown files (final version).
Handles large single INSERT statements with thousands of rows.
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

        # Handle escapes
        if escape_next:
            current_field.append(char)
            escape_next = False
            i += 1
            continue

        if char == '\\' and in_string:
            # Check if this is actually an escape or just a backslash
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

        # Handle quotes
        if char == "'":
            if not in_string:
                in_string = True
            else:
                # Check if it's escaped (two quotes in a row)
                if i + 1 < len(values_text) and values_text[i + 1] == "'":
                    current_field.append("'")
                    i += 2
                    continue
                in_string = False
            i += 1
            continue

        # Handle structure when not in string
        if not in_string:
            if char == '(':
                depth += 1
                if depth == 1:
                    # Start of new row
                    current_row = []
                    current_field = []
                i += 1
                continue

            elif char == ')':
                depth -= 1
                if depth == 0:
                    # End of row
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
                # End of field
                field_val = ''.join(current_field).strip()
                current_row.append(field_val)
                current_field = []
                i += 1
                continue

            elif char in [' ', '\n', '\r', '\t'] and depth == 0:
                # Skip whitespace between rows
                i += 1
                continue

        # Add to current field
        current_field.append(char)
        i += 1

    return rows


def parse_field_value(val):
    """Parse a field value from SQL."""
    val = val.strip()
    if val == 'NULL' or val == '':
        return None

    # Unescape - order matters! Do backslash-backslash first
    val = val.replace('\\\\', '\x00')  # Temporary placeholder for literal backslash
    val = val.replace("\\'", "'")
    val = val.replace('\\"', '"')
    val = val.replace('\\n', '\n')
    val = val.replace('\\r', '\r')
    val = val.replace('\\t', '\t')
    val = val.replace('\\0', '')
    val = val.replace('\x00', '\\')  # Restore literal backslashes

    return val


def parse_sql_file(sql_path):
    """Parse SQL file and extract node data and bodies."""

    print(f"Parsing {sql_path}...")
    print("This may take several minutes...")

    nodes = {}
    bodies = {}
    paths = {}

    with open(sql_path, 'r', encoding='utf-8', errors='ignore') as f:
        current_table = None
        buffer = []
        line_count = 0

        for line in f:
            line_count += 1
            if line_count % 100000 == 0:
                print(f"  Processed {line_count:,} lines...")

            # Detect table INSERT statements
            if line.startswith('INSERT INTO') and 'node_field_data' in line:
                if current_table and buffer:
                    # Process previous buffer
                    if current_table == 'node__body':
                        print(f"  Parsing {len(buffer)} lines of body data (node__body)...")
                        parse_body_insert(buffer, bodies)
                    elif current_table == 'node__field_body':
                        print(f"  Parsing {len(buffer)} lines of body data (node__field_body)...")
                        parse_field_body_insert(buffer, bodies)
                    elif current_table == 'path_alias':
                        print(f"  Parsing {len(buffer)} lines of path alias data...")
                        parse_path_alias_insert(buffer, paths)
                    elif current_table == 'node__field_question':
                        print(f"  Parsing {len(buffer)} lines of question data...")
                        parse_field_question_insert(buffer, bodies)
                    elif current_table == 'node__field_answer':
                        print(f"  Parsing {len(buffer)} lines of answer data...")
                        parse_field_answer_insert(buffer, bodies)
                current_table = 'node_field_data'
                buffer = [line]
            elif line.startswith('INSERT INTO') and line.find('node__body') > 0 and line.find('node__field_body') < 0:
                if current_table and buffer:
                    # Process previous buffer
                    if current_table == 'node_field_data':
                        print(f"  Parsing {len(buffer)} lines of node data...")
                        parse_node_insert(buffer, nodes)
                    elif current_table == 'node__field_body':
                        print(f"  Parsing {len(buffer)} lines of body data (node__field_body)...")
                        parse_field_body_insert(buffer, bodies)
                    elif current_table == 'path_alias':
                        print(f"  Parsing {len(buffer)} lines of path alias data...")
                        parse_path_alias_insert(buffer, paths)
                    elif current_table == 'node__field_question':
                        print(f"  Parsing {len(buffer)} lines of question data...")
                        parse_field_question_insert(buffer, bodies)
                    elif current_table == 'node__field_answer':
                        print(f"  Parsing {len(buffer)} lines of answer data...")
                        parse_field_answer_insert(buffer, bodies)
                current_table = 'node__body'
                buffer = [line]
            elif line.startswith('INSERT INTO') and 'node__field_body' in line:
                if current_table and buffer:
                    # Process previous buffer
                    if current_table == 'node_field_data':
                        print(f"  Parsing {len(buffer)} lines of node data...")
                        parse_node_insert(buffer, nodes)
                    elif current_table == 'node__body':
                        print(f"  Parsing {len(buffer)} lines of body data (node__body)...")
                        parse_body_insert(buffer, bodies)
                    elif current_table == 'path_alias':
                        print(f"  Parsing {len(buffer)} lines of path alias data...")
                        parse_path_alias_insert(buffer, paths)
                    elif current_table == 'node__field_question':
                        print(f"  Parsing {len(buffer)} lines of question data...")
                        parse_field_question_insert(buffer, bodies)
                    elif current_table == 'node__field_answer':
                        print(f"  Parsing {len(buffer)} lines of answer data...")
                        parse_field_answer_insert(buffer, bodies)
                current_table = 'node__field_body'
                buffer = [line]
            elif line.startswith('INSERT INTO') and 'path_alias' in line and 'migrate' not in line:
                if current_table and buffer:
                    # Process previous buffer
                    if current_table == 'node_field_data':
                        print(f"  Parsing {len(buffer)} lines of node data...")
                        parse_node_insert(buffer, nodes)
                    elif current_table == 'node__body':
                        print(f"  Parsing {len(buffer)} lines of body data (node__body)...")
                        parse_body_insert(buffer, bodies)
                    elif current_table == 'node__field_body':
                        print(f"  Parsing {len(buffer)} lines of body data (node__field_body)...")
                        parse_field_body_insert(buffer, bodies)
                    elif current_table == 'node__field_question':
                        print(f"  Parsing {len(buffer)} lines of question data...")
                        parse_field_question_insert(buffer, bodies)
                    elif current_table == 'node__field_answer':
                        print(f"  Parsing {len(buffer)} lines of answer data...")
                        parse_field_answer_insert(buffer, bodies)
                current_table = 'path_alias'
                buffer = [line]
            elif line.startswith('INSERT INTO') and 'node__field_question' in line:
                if current_table and buffer:
                    # Process previous buffer
                    if current_table == 'node_field_data':
                        print(f"  Parsing {len(buffer)} lines of node data...")
                        parse_node_insert(buffer, nodes)
                    elif current_table == 'node__body':
                        print(f"  Parsing {len(buffer)} lines of body data (node__body)...")
                        parse_body_insert(buffer, bodies)
                    elif current_table == 'node__field_body':
                        print(f"  Parsing {len(buffer)} lines of body data (node__field_body)...")
                        parse_field_body_insert(buffer, bodies)
                    elif current_table == 'path_alias':
                        print(f"  Parsing {len(buffer)} lines of path alias data...")
                        parse_path_alias_insert(buffer, paths)
                    elif current_table == 'node__field_answer':
                        print(f"  Parsing {len(buffer)} lines of answer data...")
                        parse_field_answer_insert(buffer, bodies)
                current_table = 'node__field_question'
                buffer = [line]
            elif line.startswith('INSERT INTO') and 'node__field_answer' in line:
                if current_table and buffer:
                    # Process previous buffer
                    if current_table == 'node_field_data':
                        print(f"  Parsing {len(buffer)} lines of node data...")
                        parse_node_insert(buffer, nodes)
                    elif current_table == 'node__body':
                        print(f"  Parsing {len(buffer)} lines of body data (node__body)...")
                        parse_body_insert(buffer, bodies)
                    elif current_table == 'node__field_body':
                        print(f"  Parsing {len(buffer)} lines of body data (node__field_body)...")
                        parse_field_body_insert(buffer, bodies)
                    elif current_table == 'path_alias':
                        print(f"  Parsing {len(buffer)} lines of path alias data...")
                        parse_path_alias_insert(buffer, paths)
                    elif current_table == 'node__field_question':
                        print(f"  Parsing {len(buffer)} lines of question data...")
                        parse_field_question_insert(buffer, bodies)
                current_table = 'node__field_answer'
                buffer = [line]
            elif current_table:
                buffer.append(line)

                # Check if INSERT is complete (ends with semicolon)
                if line.rstrip().endswith(';'):
                    if current_table == 'node_field_data':
                        print(f"  Parsing {len(buffer)} lines of node data...")
                        parse_node_insert(buffer, nodes)
                    elif current_table == 'node__body':
                        print(f"  Parsing {len(buffer)} lines of body data (node__body)...")
                        parse_body_insert(buffer, bodies)
                    elif current_table == 'node__field_body':
                        print(f"  Parsing {len(buffer)} lines of body data (node__field_body)...")
                        parse_field_body_insert(buffer, bodies)
                    elif current_table == 'path_alias':
                        print(f"  Parsing {len(buffer)} lines of path alias data...")
                        parse_path_alias_insert(buffer, paths)
                    elif current_table == 'node__field_question':
                        print(f"  Parsing {len(buffer)} lines of question data...")
                        parse_field_question_insert(buffer, bodies)
                    elif current_table == 'node__field_answer':
                        print(f"  Parsing {len(buffer)} lines of answer data...")
                        parse_field_answer_insert(buffer, bodies)

                    current_table = None
                    buffer = []

    # Process any remaining buffer
    if current_table and buffer:
        if current_table == 'node_field_data':
            parse_node_insert(buffer, nodes)
        elif current_table == 'node__body':
            parse_body_insert(buffer, bodies)
        elif current_table == 'node__field_body':
            parse_field_body_insert(buffer, bodies)
        elif current_table == 'path_alias':
            parse_path_alias_insert(buffer, paths)
        elif current_table == 'node__field_question':
            parse_field_question_insert(buffer, bodies)
        elif current_table == 'node__field_answer':
            parse_field_answer_insert(buffer, bodies)

    print(f"\n✓ Extracted {len(nodes):,} nodes, {len(bodies):,} bodies, and {len(paths):,} URL paths")
    return nodes, bodies, paths


def parse_node_insert(lines, nodes):
    """Parse node_field_data INSERT statement."""
    full_text = ''.join(lines)

    # Find VALUES section
    match = re.search(r'VALUES\s+(.+);?\s*$', full_text, re.DOTALL)
    if not match:
        return

    values_text = match.group(1).rstrip(';')
    rows = extract_row_tuples(values_text)

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
            except (ValueError, IndexError, TypeError) as e:
                pass


def parse_body_insert(lines, bodies):
    """Parse node__body INSERT statement (typically author bios/descriptions)."""
    full_text = ''.join(lines)

    # Find VALUES section
    match = re.search(r'VALUES\s+(.+);?\s*$', full_text, re.DOTALL)
    if not match:
        return

    values_text = match.group(1).rstrip(';')
    rows = extract_row_tuples(values_text)

    print(f"    Found {len(rows)} body rows")

    for row in rows:
        if len(row) >= 7:
            try:
                nid = int(parse_field_value(row[2]))  # entity_id is 3rd field
                if nid not in bodies:
                    bodies[nid] = {}
                bodies[nid]['bio'] = parse_field_value(row[6])  # body_value is 7th field
                bodies[nid]['summary'] = parse_field_value(row[7]) if len(row) > 7 else None
            except (ValueError, IndexError, TypeError) as e:
                continue


def parse_field_body_insert(lines, bodies):
    """Parse node__field_body INSERT statement (actual full content)."""
    full_text = ''.join(lines)

    # Find VALUES section
    match = re.search(r'VALUES\s+(.+);?\s*$', full_text, re.DOTALL)
    if not match:
        return

    values_text = match.group(1).rstrip(';')
    rows = extract_row_tuples(values_text)

    print(f"    Found {len(rows)} field_body rows")

    for row in rows:
        if len(row) >= 7:
            try:
                nid = int(parse_field_value(row[2]))  # entity_id is 3rd field
                if nid not in bodies:
                    bodies[nid] = {}
                # Store the main content - this is the primary body text
                bodies[nid]['value'] = parse_field_value(row[6])  # field_body_value is 7th field
            except (ValueError, IndexError, TypeError) as e:
                continue


def parse_path_alias_insert(lines, paths):
    """Parse path_alias INSERT statement for URLs."""
    full_text = ''.join(lines)

    # Find VALUES section
    match = re.search(r'VALUES\s+(.+);?\s*$', full_text, re.DOTALL)
    if not match:
        return

    values_text = match.group(1).rstrip(';')
    rows = extract_row_tuples(values_text)

    print(f"    Found {len(rows)} path alias rows")

    for row in rows:
        if len(row) >= 6:
            try:
                # Format: (id, revision_id, uuid, langcode, path, alias, status)
                path = parse_field_value(row[4])  # internal path like /node/123
                alias = parse_field_value(row[5])  # URL alias like /blog/my-post

                # Extract node ID from path
                if path and path.startswith('/node/'):
                    nid = int(path.replace('/node/', ''))
                    if alias:
                        paths[nid] = alias
            except (ValueError, IndexError, TypeError) as e:
                continue


def parse_field_question_insert(lines, bodies):
    """Parse node__field_question INSERT statement (Q&A question text)."""
    full_text = ''.join(lines)

    # Find VALUES section
    match = re.search(r'VALUES\s+(.+);?\s*$', full_text, re.DOTALL)
    if not match:
        return

    values_text = match.group(1).rstrip(';')
    rows = extract_row_tuples(values_text)

    print(f"    Found {len(rows)} field_question rows")

    for row in rows:
        if len(row) >= 7:
            try:
                nid = int(parse_field_value(row[2]))  # entity_id is 3rd field
                if nid not in bodies:
                    bodies[nid] = {}
                # Store the question text
                bodies[nid]['question'] = parse_field_value(row[6])  # field_question_value is 7th field
            except (ValueError, IndexError, TypeError) as e:
                continue


def parse_field_answer_insert(lines, bodies):
    """Parse node__field_answer INSERT statement (Q&A answer text)."""
    full_text = ''.join(lines)

    # Find VALUES section
    match = re.search(r'VALUES\s+(.+);?\s*$', full_text, re.DOTALL)
    if not match:
        return

    values_text = match.group(1).rstrip(';')
    rows = extract_row_tuples(values_text)

    print(f"    Found {len(rows)} field_answer rows")

    for row in rows:
        if len(row) >= 7:
            try:
                nid = int(parse_field_value(row[2]))  # entity_id is 3rd field
                if nid not in bodies:
                    bodies[nid] = {}
                # Store the answer text
                bodies[nid]['answer'] = parse_field_value(row[6])  # field_answer_value is 7th field
            except (ValueError, IndexError, TypeError) as e:
                continue


def preprocess_html(html_content):
    """Preprocess HTML to convert custom Drupal elements to standard HTML."""
    if not html_content:
        return html_content

    try:
        soup = BeautifulSoup(html_content, 'html.parser')

        # Convert <div class="subhead"> to <h2>
        for div in soup.find_all('div', class_='subhead'):
            h2 = soup.new_tag('h2')
            h2.string = div.get_text()
            div.replace_with(h2)

        # Convert <div class="pull"> to <blockquote>
        for div in soup.find_all('div', class_='pull'):
            blockquote = soup.new_tag('blockquote')
            blockquote.string = div.get_text()
            div.replace_with(blockquote)

        # Return the content without html/body wrappers if they were added
        # Check if soup has html/body wrappers and extract just the content
        if soup.body:
            return ''.join(str(tag) for tag in soup.body.children)
        else:
            return str(soup)
    except Exception as e:
        # If preprocessing fails, return original HTML
        return html_content


def export_to_hugo(nodes, bodies, paths, output_dir="content"):
    """Export parsed data to Hugo markdown files."""

    print(f"\nCreating Hugo markdown files...")

    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    stats = defaultdict(int)
    processed = 0
    with_body = 0
    with_bio = 0
    with_qa = 0

    for nid, node in nodes.items():
        # Only export published nodes
        if not node['status']:
            continue

        content_type = node['type']
        if not content_type:
            continue

        # Create directory for content type
        type_dir = output_path / content_type.replace('_', '-')
        type_dir.mkdir(exist_ok=True)

        # Track stats
        stats[content_type] += 1

        # Get body content
        body_data = bodies.get(nid, {})
        body_html = body_data.get('value', '') or ''
        summary_html = body_data.get('summary', '') or ''
        bio_html = body_data.get('bio', '') or ''
        question_html = body_data.get('question', '') or ''
        answer_html = body_data.get('answer', '') or ''

        if body_html:
            with_body += 1
        if bio_html:
            with_bio += 1
        if question_html and answer_html:
            with_qa += 1

        # Preprocess HTML to convert custom Drupal elements
        body_html = preprocess_html(body_html)
        summary_html = preprocess_html(summary_html)
        bio_html = preprocess_html(bio_html)
        question_html = preprocess_html(question_html)
        answer_html = preprocess_html(answer_html)

        # Convert HTML to Markdown
        try:
            content = md(body_html, heading_style="ATX") if body_html else ''
            summary_md = md(summary_html, heading_style="ATX") if summary_html else ''
            bio_md = md(bio_html, heading_style="ATX") if bio_html else ''
            question_md = md(question_html, heading_style="ATX") if question_html else ''
            answer_md = md(answer_html, heading_style="ATX") if answer_html else ''
        except Exception as e:
            content = body_html
            summary_md = summary_html
            bio_md = bio_html
            question_md = question_html
            answer_md = answer_html

        # Create frontmatter
        try:
            created_date = datetime.fromtimestamp(node['created'])
            updated_date = datetime.fromtimestamp(node['changed'])
        except:
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

        if summary_md:
            frontmatter['summary'] = summary_md.strip()

        if bio_md:
            frontmatter['author_bio'] = bio_md.strip()

        # Add Q&A content if available
        if question_md:
            frontmatter['question'] = question_md.strip()

        # Add URL/permalink if available
        if nid in paths:
            frontmatter['url'] = paths[nid]

        if node.get('promote'):
            frontmatter['featured'] = True

        if node.get('sticky'):
            frontmatter['pinned'] = True

        # Determine main content: prefer answer for Q&A types, otherwise use body
        main_content = content
        if answer_md and not content:
            main_content = answer_md
        elif answer_md and content:
            # If both exist, combine them with answer first
            main_content = f"{answer_md}\n\n---\n\n{content}"

        # Create filename
        slug = slugify(node['title'])
        if not slug:
            slug = f"node-{nid}"

        filename = f"{slug}-{nid}.md"
        filepath = type_dir / filename

        # Write file
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('---\n')
                yaml.dump(frontmatter, f, allow_unicode=True,
                         default_flow_style=False, sort_keys=False)
                f.write('---\n\n')
                if main_content:
                    f.write(main_content)

            processed += 1
            if processed % 500 == 0:
                print(f"  Created {processed:,} files...")

        except Exception as e:
            print(f"  Error writing {filepath}: {e}")

    # Print statistics
    print(f"\n✓ Created {processed:,} markdown files")
    print(f"  - {with_body:,} with body content")
    print(f"  - {with_bio:,} with author bio/description")
    print(f"  - {with_qa:,} with Q&A content (question + answer)")
    print("\nContent by type:")
    for content_type, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
        dir_path = output_path / content_type.replace('_', '-')
        print(f"  {content_type:30s}: {count:5,} files in {dir_path}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Convert Drupal SQL dump to Hugo markdown')
    parser.add_argument('--sql', default='th_db.sql', help='Path to SQL dump file')
    parser.add_argument('--output', default='content', help='Output directory for Hugo content')

    args = parser.parse_args()

    nodes, bodies, paths = parse_sql_file(args.sql)
    export_to_hugo(nodes, bodies, paths, args.output)

    print(f"\n✓ Conversion complete! Files written to {args.output}/")
