# Content remediation tracker

This workflow tracks the defects identified during the TeachingHistory.org
category review and reconciles them against the current Hugo repository.

## Local inputs and generated files

- The locally supplied `THist Category Review.xlsx` workbook is the source. Only
  its `consolidated to-fix list` sheet is in scope.
- A normalized tracker CSV supplies stable IDs, source-row references, scope,
  workstream, status, evidence, and the corresponding GitHub issue.
- The content audit writes CSV and Markdown results to `reports/` by default.
- The field inventory writes table schemas and source row counts to `reports/`.
- `utils/tests/fixtures/content_remediation_pages.csv` fixes the expected Hugo
  paths and legacy routes for the eleven representative Drupal nodes named in
  issue #24.

The source workbook, normalized tracker, and generated `reports/` directory are
git-ignored local artifacts. Do not edit generated audit columns by hand.

## Run the audit

From the repository root:

```sh
just content-audit path/to/content_remediation_tracker.csv
```

Or run the script directly:

```sh
python3 utils/content_remediation_audit.py \
  --tracker path/to/content_remediation_tracker.csv
```

To regenerate the field inventory when a Drupal SQL dump is available:

```sh
just drupal-field-inventory path/to/th_db.sql
```

The audit is read-only with respect to Hugo content. It:

1. indexes Markdown by frontmatter URL and Drupal node ID;
2. also recognizes Hugo aliases and routes implied by filenames and section
   indexes;
3. distinguishes source-extraction and asset-mapping defects from Hugo
   rendering, external-media, and cross-layer verification work;
4. maps page-specific tracker rows to content files;
5. flags suspiciously short bodies, repeated substantial body sections,
   missing local files and image assets, and case-mismatched asset paths; and
6. writes deterministic CSV and Markdown reports.

Automated flags are evidence for review, not final dispositions. Global and
category-wide tracker items may not correspond to a single Markdown file.

## Status conventions

- **Open**: confirmed work remains.
- **Needs verification**: previous work may have resolved the item, but it needs
  a targeted check.
- **In progress**: an existing workstream is already active.
- **Partial**: part of the requested behavior or content exists.
- **Resolved**: current repository evidence supports closure.
- **Duplicate**: another tracker row represents the same underlying defect.

The workstream issues are linked from GitHub issue #19. Issue #24 owns the local
tracker reconciliation and audit tooling; implementation remains in the linked
workstream issues.
