# Content remediation tracker

This workflow tracks the defects identified during the TeachingHistory.org
category review and reconciles them against the current Hugo repository.

## Source and generated files

- The locally supplied `THist Category Review.xlsx` workbook is the source. Only
  its `consolidated to-fix list` sheet is in scope; the complete workbook is not
  committed because its other editorial tabs are unrelated to this audit.
- `reports/content_remediation_tracker.xlsx` is the focused, human-facing
  `Remediation Tracker`. It adds stable IDs, source-row references, scope,
  workstream, current status, evidence, and the corresponding GitHub issue.
- `reports/content_remediation_tracker.csv` is the diffable representation used
  by repository tooling.
- `reports/content_remediation_audit.csv` adds the matched Hugo content file,
  Drupal node ID, and automated audit flags.
- `reports/content_remediation_audit.md` summarizes the latest audit run.

The focused workbook is the human-facing tracker and the normalized CSV is the
machine-readable planning input. Do not edit generated audit columns by hand.

## Run the audit

From the repository root:

```sh
just content-audit
```

Or run the script directly:

```sh
python3 utils/content_remediation_audit.py
```

The audit is read-only with respect to Hugo content. It:

1. indexes Markdown by frontmatter URL and Drupal node ID;
2. also recognizes routes implied by Hugo filenames and section indexes;
3. maps page-specific tracker rows to content files;
4. flags suspiciously short bodies, repeated substantial body sections, and
   missing local image assets; and
5. writes deterministic CSV and Markdown reports.

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

The workstream issues are linked from GitHub issue #19. Issue #24 owns tracker
reconciliation and audit tooling; implementation remains in the linked
workstream issues.
