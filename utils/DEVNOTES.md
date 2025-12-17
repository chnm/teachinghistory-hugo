# Developer Notes: Drupal to Hugo Conversion

## Overview

This directory contains the Drupal-to-Hugo conversion script for the Teaching History website migration. The script parses a Drupal 8/9 SQL database dump and converts content to Hugo-compatible Markdown files.

## Scripts

### drupal_to_hugo.py

Primary conversion script that processes the Drupal SQL dump without requiring a running database server.

**Usage:**
```bash
uv run python drupal_to_hugo.py --sql th_db.sql --output content
```

**Options:**
- `--sql` - Path to the SQL dump file (default: th_db.sql)
- `--output` - Output directory for generated Markdown files (default: content)

## Environment Setup

**Install dependencies:**
```bash
uv pip install markdownify pyyaml beautifulsoup4
```

The script requires Python 3.x and uses `uv` for package management. A virtual environment is located at `../.venv`.

## Data Sources

The script extracts data from the following Drupal tables:

1. **node_field_data** - Core node metadata (titles, dates, content types, status)
2. **node__body** - Author biographies and descriptions
3. **node__field_body** - Primary article/page content
4. **node__field_question** - Question text for Q&A content types
5. **node__field_answer** - Answer text for Q&A content types
6. **path_alias** - URL aliases for redirects

## Key Features

### HTML Preprocessing

The script preprocesses Drupal-specific HTML elements before Markdown conversion:

- `<div class="subhead">` → `<h2>` (converted to `## Markdown headers`)
- `<div class="pull">` → `<blockquote>` (converted to `> blockquotes`)

This preprocessing occurs in the `preprocess_html()` function using BeautifulSoup.

### Character Escaping

The `parse_field_value()` function handles SQL escape sequences:
- `\"` → `"`
- `\'` → `'`
- `\\` → `\`
- `\n`, `\r`, `\t` → newlines, returns, tabs

Proper unescaping of double quotes is critical for HTML attribute parsing.

### Field Priority

For nodes with multiple body fields:
1. `node__field_body` is used as main content
2. `node__body` is stored as `author_bio` in frontmatter
3. Both can coexist in the same node

For Q&A content types:
1. Question stored in `question` frontmatter field
2. Answer used as main body content

## Output Format

Generated Markdown files include:

**Frontmatter (YAML):**
- `title` - Node title
- `date` - Creation date (ISO 8601)
- `lastmod` - Last modified date (ISO 8601)
- `type` - Content type (Drupal type with underscores converted to hyphens)
- `draft` - Always false (only published nodes are exported)
- `drupal_nid` - Original Drupal node ID (for URL mapping)
- `url` - Original URL path (if path_alias exists)
- `author_bio` - Author biography (if present)
- `question` - Question text (Q&A content types only)
- `summary` - Content summary (if present)
- `featured` - Boolean (if Drupal promote flag set)
- `pinned` - Boolean (if Drupal sticky flag set)

**Body Content:**
Markdown-converted HTML from primary body field.

## File Organization

Output files are organized by content type:
```
content/
├── blog/
├── ask-an-educator/
├── historical-site/
├── teaching-standard/
└── [39 other content types]/
```

**Naming convention:** `{slug}-{drupal_nid}.md`

The slug is generated from the title (lowercase, URL-safe, max 100 characters). The Drupal NID is appended to ensure uniqueness.

## Statistics

From the 833MB SQL dump:
- 16,764 total nodes
- 9,604 published nodes converted
- 1,445 files with body content (15%)
- 270 files with Q&A content
- 105 files with author bios
- 3,724 URL mappings extracted

Many content types (reference nodes, taxonomy terms, redirects) do not contain body content by design.

## Performance Notes

The script processes the 833MB SQL file in approximately 2-3 minutes on modern hardware. It uses line-by-line processing to manage memory efficiently and handles multi-line INSERT statements through a buffering system.

## Known Limitations

1. Only specific custom fields are extracted (body, field_body, question, answer)
2. Other custom fields remain in the SQL dump and require additional parsing functions
3. Media files and images are not migrated (need separate extraction)
4. Internal links and image paths may need updating for Hugo

## Extending the Script

To extract additional custom fields:

1. Identify the table name:
   ```bash
   grep "^CREATE TABLE \`node__field" th_db.sql | grep "description"
   ```

2. Add a parsing function following the pattern in `parse_field_body_insert()`

3. Update `parse_sql_file()` to detect and process the new table

4. Update `export_to_hugo()` to include the field in frontmatter or body content

## Troubleshooting

**Missing headers in output:**
Verify that `parse_field_value()` is unescaping double quotes (`\"`) correctly. BeautifulSoup requires valid HTML to parse class attributes.

**Missing body content:**
Check which table contains the content (`node__body` vs `node__field_body`). Some content types use alternative field names.

**Encoding errors:**
The script uses `encoding='utf-8', errors='ignore'` when reading the SQL file. Some characters may be dropped if not valid UTF-8.
