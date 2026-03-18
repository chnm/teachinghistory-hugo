# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Drupal-to-Hugo conversion project for Teaching History (CHNM). The primary goal was to migrate content from a large Drupal SQL database (833MB, 16,764 nodes) to Hugo-compatible markdown files. The conversion has been completed with 9,604 published nodes successfully converted.

## Key Architecture

### Conversion Script: `drupal_to_hugo.py`

The conversion script uses a **direct SQL parsing approach** without requiring a database server:

1. **Three-stage parsing**: Extracts data from three Drupal tables:
   - `node_field_data` - Core node metadata (title, type, dates, status)
   - `node__body` - Body content (primary source)
   - `node__field_body` - Alternative body field (fallback)

2. **SQL parsing strategy**: The script handles large multi-row INSERT statements by:
   - Using a custom `extract_row_tuples()` parser that tracks parentheses depth, string boundaries, and escape sequences
   - Processing the SQL file line-by-line to manage memory efficiently
   - Buffering INSERT statements that span multiple lines

3. **Content transformation**:
   - HTML → Markdown conversion using `markdownify` library
   - Slug generation from titles (100 char limit, URL-safe)
   - Timestamp conversion from Unix epoch to ISO 8601
   - Frontmatter generation with YAML format

### Content Structure

Generated content lives in `content/` with 42 content types, organized as:
```
content/
├── historical-site/        (3,467 files - largest collection)
├── history-in-multimedia/  (1,665 files)
├── tah-grant/              (1,143 files)
├── website/                (1,059 files)
└── [38 more content types]
```

**File naming convention**: `{slug}-{drupal_nid}.md`
- The `drupal_nid` preserves the original Drupal node ID for URL mapping

**Frontmatter fields**:
- `title`, `date`, `lastmod`, `type`, `draft`, `drupal_nid` - Always present
- `featured` - Set if Drupal `promote` flag was true
- `pinned` - Set if Drupal `sticky` flag was true
- `summary` - Included if Drupal summary field had content

### Known Data Characteristics

- **Body content coverage**: Only ~16% (1,550 files) have body content
- **Empty nodes are expected**: Many content types (reference nodes, taxonomy, redirects, media) don't use body fields
- **Custom fields not extracted**: Only `body` and `field_body` are currently parsed. Other custom fields (like `field_description`, `field_text`) remain in the SQL dump

## Development Commands

### Running the Conversion

```bash
# Activate virtual environment
source .venv/bin/activate

# Run conversion (will take several minutes)
python drupal_to_hugo.py --sql th_db.sql --output content

# With custom paths
python drupal_to_hugo.py --sql /path/to/dump.sql --output /path/to/output
```

### Python Environment

This project uses `uv` for package management. Dependencies:
- `markdownify` - HTML to Markdown conversion
- `pyyaml` - YAML frontmatter generation
- `beautifulsoup4` - HTML parsing (markdownify dependency)

To install dependencies:
```bash
uv pip install markdownify pyyaml
```

## Important Implementation Details

### SQL Parsing Edge Cases

The `extract_row_tuples()` function handles several complex scenarios:
- Escaped single quotes (`''` and `\'`)
- Backslashes in content (`\\`)
- Commas and parentheses within string values
- Multi-kilobyte text fields spanning multiple lines
- Mixed escape sequences (`\n`, `\r`, `\t`, `\0`)

### Body Field Priority

The script checks two body field tables with this precedence:
1. `node__body` is parsed first and takes priority
2. `node__field_body` is used as fallback (only if nid not already in bodies dict)

This prevents overwriting longer/better content with shorter alternatives.

### Content Type Mapping

Drupal content types use underscores (`teaching_standard`), Hugo directories use hyphens (`teaching-standard`). The conversion applies `replace('_', '-')` consistently.

## Common Tasks

### Re-running Conversion

```bash
# Clean existing content
rm -rf content

# Run fresh conversion
python drupal_to_hugo.py --sql th_db.sql --output content
```

### Extracting Additional Fields

To add custom field extraction (e.g., `field_description`):

1. Find the table name in SQL dump:
   ```bash
   grep "^CREATE TABLE \`node__field" th_db.sql | grep "description"
   ```

2. Add a new parsing function following the `parse_body_insert()` pattern in `drupal_to_hugo.py`

3. Update the table detection logic in `parse_sql_file()` to buffer and process the new table

### Analyzing Content Distribution

```bash
# Count files by content type
find content -type d -maxdepth 1 -exec sh -c 'echo "$(find "$1" -name "*.md" | wc -l) $1"' _ {} \; | sort -rn

# Find files with body content
grep -l "^---$" content/*/*.md | head -20

# Check frontmatter of a specific file
head -20 content/blog/some-file-12345.md
```

## Next Steps for Hugo Migration

1. **Hugo configuration**: Create `hugo.toml` with taxonomies and content type settings
2. **Theme setup**: Install or create Hugo theme with layouts for 42 content types
3. **Media migration**: Extract Drupal files directory and place in Hugo's `static/`
4. **URL mapping**: Use `drupal_nid` frontmatter field to create redirects from old URLs
5. **Custom layouts**: Special content types (quizly, webform) need custom templates
6. **Image path rewriting**: Update internal links and image references in markdown content

## Logs and Documentation

- `conversion.log` - Detailed conversion output with row counts and processing stats
- `CONVERSION_SUMMARY.md` - Human-readable summary of conversion results and next steps
- Both regenerated on each conversion run
