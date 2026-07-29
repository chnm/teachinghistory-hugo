# Sheet-Driven Apply Step — Design

**Date:** 2026-07-21
**Status:** Approved design
**Scope:** The `apply` subcommand that enacts the team's decisions from the
review sheets; successor to the triage builds (see
`2026-07-07-link-review-triage-design.md`,
`2026-07-20-rebrand-triage-and-page-sheet-design.md`)
**Related:** `utils/link_checker.py`, `utils/link_review_master.xlsx`,
`utils/link_review_pages.xlsx`, `utils/Link Check & Review Process.md`

---

## Purpose

The review sheets now carry a `decision` dropdown (link-level:
`remove` / `update-to-final-url` / `salvage-wayback` / `salvage-new-link` /
`keep`; page-level: `delete-page` / `salvage-wayback` / `fix-links` / `keep`).
Nothing yet acts on those decisions. This build adds
`uv run utils/link_checker.py apply` — dry-run by default, `--apply` to
mutate — so decisions can be enacted the day the sheets come back. Built
against synthetic decisions now; fine-tuned against the real sheets later.

## Decisions (from brainstorming)

1. **`new_url` column added to the master sheet now**, before the team edits
   it (regenerating later would clobber entered decisions). `salvage-new-link`
   reads its replacement URL from this column — no cell-comment parsing.
2. **`delete-page` sets `draft: true`** in the page's frontmatter rather than
   deleting the file — reversible piecemeal and easy to audit. The file stays;
   Hugo stops publishing it.
3. **Architecture: one `apply` subcommand** (not split page/link commands, not
   a separate compile stage). Dry-run writes the plan artifact; `--apply`
   executes the same resolved plan. Matches the existing `replace` pattern.
4. **Page decisions cascade as defaults; explicit link decisions override**
   (most-specific wins). This is what makes bulk page-level review work — the
   team does not fill five master rows per page.

## Inputs

`apply` reads **both xlsx files** with openpyxl (the CSVs never carry
decisions):

- `utils/link_review_master.xlsx` — rows keyed by (`source_file`,
  `link_url`); consumes `decision`, `new_url`, plus existing columns
  (`link_kind`, `final_url`, `wayback_url`, `wayback_status`,
  `broken_category`, `rebrand_verdict`).
- `utils/link_review_pages.xlsx` — rows keyed by `source_file`; consumes
  `decision`.

**Validation before anything else:** any non-blank decision outside its
sheet's vocabulary aborts the run with a list of offending cells (sheet, row,
value). Blank decision = no action. Duplicate keys abort with a message.

## Resolution semantics

Evaluated per page, most-specific wins:

1. Page `delete-page` → draft the page; **all** link-level decisions on that
   page are superseded (reported as `superseded`, never silently dropped).
2. Page `salvage-wayback` → default action for that page's *broken* links
   (`broken_category == "A"` or `rebrand_verdict == "probably-broken"`): swap
   to their `wayback_url`. Broken links without a snapshot → `unresolved`.
   Non-broken links: no default.
3. Page `fix-links`, `keep`, or blank → no page-level default.
4. An explicit link-level decision always overrides its page's default.

Link-level actions:

| decision | action |
|---|---|
| `remove` | `link_kind == "hyperlink"` → keep the text, drop the link markup; `bare_url` → delete the URL text |
| `update-to-final-url` | replace the URL with the row's `final_url` (blank `final_url` → `unresolved`) |
| `salvage-wayback` | replace the URL with the row's `wayback_url` (blank → `unresolved`) |
| `salvage-new-link` | replace the URL with the row's `new_url` (blank or not http(s) → `unresolved`) |
| `keep` | no-op |

## Mutation engine

Per affected file (grouped, one read/write per file):

- **URL replacement:** plain-string swap of old URL → new URL, the proven
  `run_replace` approach. Old URL absent from the file → `skipped:not-found`,
  reported, never guessed.
- **Unlink:** handles the three link forms `extract` already recognizes —
  `[text](url)` → `text`; `<a href="url">text</a>` → `text`; bare URL →
  remove the URL string.
- **Draft:** parse the YAML frontmatter, set `draft: true`, preserve all
  other fields and the body byte-for-byte.

Files with no resolved actions are never opened for writing. No network
anywhere in `apply`.

## Outputs

- **Dry-run (default):** console summary (counts per action, per section) +
  `utils/link_apply_plan.csv` — one row per planned mutation: `source_file`,
  `action`, `link_url`, `new_value`, `driver` (`link-row` | `page-cascade`),
  `status` (`planned` | `unresolved:<reason>` | `superseded` |
  `skipped:<reason>`).
- **`--apply`:** executes the same resolved plan, rewrites the CSV with
  `status` reflecting what happened (`applied` / `skipped:<reason>` / …), and
  prints the summary. The plan CSV is the audit artifact either way.

## Safety rails

- Dry-run is the default; `--apply` is required to touch content.
- Validation failures abort before any file is opened.
- Git is the rollback story; `apply` makes no commits itself.
- The command never re-runs network checks or alters the review sheets.

## Out of scope

- Acting on `blocked-unknown` / `needs-human` rows without decisions.
- Cleaning up empty sections/paragraphs left after unlinking (report-only;
  human polish if needed).
- Committing or building the site after mutation.
- Any change to the classify/pages generation logic (other than the
  `new_url` blank column).

## Testing / verification

Unit tests (extend `utils/tests/test_link_review.py`):

1. Decision parsing/validation: valid vocab passes; typo aborts with cell
   reference; blank = no action; duplicate keys abort.
2. Cascade resolution: link override beats page default; `delete-page`
   supersedes link rows; page `salvage-wayback` targets only broken links;
   missing snapshot/new_url/final_url → `unresolved`.
3. Text transforms: unlink for all three link forms; URL swap; URL absent →
   skipped; draft flip preserves other frontmatter and body.
4. `new_url` blank column present in regenerated master xlsx (writer test).

Integration: temp content dir + synthetic xlsx sheets → dry-run plan CSV
matches expectations; `--apply` mutates only the expected files; re-running
dry-run afterward reports the already-applied URLs as `skipped:not-found`.

Real-data smoke test (no `--apply`): run dry-run against the real sheets with
zero decisions filled → plan is empty, exits cleanly.

## Status & handoff

Design approved 2026-07-21. Next: implementation plan via writing-plans.
The `new_url` column must land and the sheets must be re-shared **before**
the team starts recording decisions.
