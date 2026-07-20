# Rebrand Triage Refinement & Page-Level Sheet — Design

**Date:** 2026-07-20
**Status:** Approved design
**Scope:** Team-feedback follow-up to the link review triage (see
`2026-07-07-link-review-triage-design.md`); responds to `feedback.md`
**Related:** `utils/link_checker.py`, `utils/link_review_master.csv`,
`utils/Link Check & Review Process.md`

---

## Purpose

The team reviewed the 500 `C-candidate` ("Rebranded") links and confirmed the
triage works. Their feedback (`feedback.md`) asks for two refinements, both of
which stay on the read-only, sheet-producing side of the pipeline:

1. **Tighten the rebrand triage** so most of the 500 C-candidates get an
   automatic verdict, shrinking the human-review pile. Two signals: does the
   final URL look like a homepage (the "content gone, only the site survives"
   pattern), and does the destination look like a history/education site.
2. **A page-level derivative sheet** — one row per *page* instead of per link —
   so the team can make bulk page-deletion calls (e.g., a Website Review whose
   reviewed link is dead and un-archivable has no remaining value; a teaching
   guide survives a few dead links).

No content is mutated. The sheet-driven `apply` step remains deferred, as
before, until the team's `decision` column exists.

## Decisions (from brainstorming)

1. **Scope:** both feedback items; `apply` step still out of scope.
2. **Homepage redirects** → `probably-broken` (not merely needs-human). The
   team identified homepage redirects as the main real-broken pattern. Wayback
   info rides alongside; a human still signs off via the sheet.
3. **Page sheet computes a suggestion** (`suggested_page_action`),
   section-aware, same advisory-only contract as the link sheet.
4. **Mechanism: deterministic rules** in the offline `classify` stage — URL
   parsing plus a curated vocabulary matched against `remote_title` and the
   final URL text. No new network requests, no LLM calls; repeatable and
   unit-testable. The feedback's "prompt Claude" intent is implemented as
   rules; the residual `needs-human` pile can be triaged interactively later.

## Feasibility (verified against current data)

All 500 C-candidate rows already have `final_url`; 432 have `remote_title`.
A prototype of the rules below run against `link_review_master.csv` yields:

- `probably-broken` (homepage-shaped final URL): **147**
- `probably-fine` (not homepage, history signal): **293**
- `needs-human` (not homepage, no signal): **60**

Human pile shrinks 500 → 60, and sampled needs-human rows are genuinely
ambiguous (news interactives, topic pages, tools) — exactly the rows that
deserve eyes. 1,206 distinct pages have ≥1 non-live link, so that is the
approximate row count of the page sheet.

## Part 1 — Rebrand triage (`classify` extension)

Two new pure helpers in `utils/link_checker.py`:

- `is_homepage_url(final_url)` — true when the URL path is empty or trivial
  (`/`, `/index.html`, `/index.htm`, `/index.php`, `/home`, `/default.aspx`,
  case-insensitive, trailing slash ignored) **and** there is no query string.
- `history_site_signal(remote_title, final_url)` — case-insensitive substring
  match of a curated vocabulary over title + final URL text; returns the list
  of matched terms (so the sheet shows *why*). Vocabulary: history, historical,
  primary source, museum, archive, education, teaching, teacher, library,
  heritage, humanities, smithsonian, social studies, civics, k-12, learning,
  lesson, curriculum, university, `.edu`, `.gov`. Rows with no `remote_title`
  still match on URL text.

**Verdict logic — C-candidate rows only** (evaluated in order):

1. `is_homepage_url(final_url)` → `rebrand_verdict = probably-broken`
2. history signal present → `probably-fine`
3. otherwise → `needs-human`

**New master-sheet columns** (appended; blank for non-C rows):

```
final_is_homepage, history_signal, rebrand_verdict
```

**`suggested_action` for C-candidate rows** becomes verdict-driven:

| verdict | suggested_action |
|---|---|
| probably-fine | `update-to-final-url` (mechanical fix: repoint link at `final_url`; executable by a future apply step) |
| probably-broken | `salvage-wayback` if a snapshot exists, else `remove-or-replace` |
| needs-human | `needs-subjective-review` (unchanged) |

All other categories' behavior is unchanged. `classify` remains a pure
offline join — no network.

## Part 2 — Page-level sheet (`pages` subcommand)

New subcommand: `uv run utils/link_checker.py pages`. Reads
`link_review_master.csv` (must exist; error with a pointer to `classify` if
not), aggregates, writes `utils/link_review_pages.csv` and
`utils/link_review_pages.xlsx` (frozen header + autofilter, matching the
master xlsx treatment).

**One row per page with ≥1 non-live link.** Columns:

- Identity: `section`, `subsection` (second path segment of `source_file`,
  empty when none), `page_title`, `page_url`, `source_file`
- Counts: `total_links`, `live`, `dead_A`, `rebrand_probably_broken`,
  `rebrand_probably_fine`, `rebrand_needs_human`, `soft404_B`,
  `blocked_unknown`, `needs_human`, `bulk_delete_candidates`
- Salvageability: `broken_with_wayback`, `broken_no_wayback` — where "broken"
  means `dead_A` + `rebrand_probably_broken`
- Verdict: `suggested_page_action`

**`suggested_page_action` logic** (evaluated in order):

1. Subsection is link-centric (`website-reviews`, `national-resources`) and
   `broken_no_wayback ≥ 1` → `delete-page-candidate`
2. Link-centric and broken links exist but all have Wayback snapshots →
   `salvage-wayback`
3. Otherwise → `fix-links-only`

Advisory only — nothing acts on this column. It lets the team filter to
`delete-page-candidate`, sanity-check, and record bulk decisions.

## Out of scope

- Any content mutation; the `apply` step (link-level or page-level deletion)
  is still a later, sheet-driven build.
- Automated verdicts for categories B/D — unchanged from the prior design.
- LLM-assisted judging of ambiguous rows (can be done interactively on the
  60-row residue if the team wants).

## Testing / verification

Extend the existing unit suite:

1. `is_homepage_url`: bare domain, trailing slash, `/index.html`, `:443`
   ports, query-string present (→ not homepage), real path (→ not homepage).
2. `history_site_signal`: title hit, URL-only hit (no title), no hit,
   matched-terms output.
3. Verdict logic: all three branches, including precedence (homepage wins even
   with a history signal).
4. `suggested_action` mapping for each verdict (with and without Wayback).
5. Page aggregation: counts, subsection derivation, and each
   `suggested_page_action` rule.

Then verify against real data:

- `classify` verdict counts match the prototype (147 / 293 / 60).
- Spot-check ~15 rows per verdict for sanity.
- Run `pages`; confirm ~1,200 rows, open the xlsx, filter to
  `delete-page-candidate` and eyeball a sample of website-reviews pages.

## Status & handoff

Design approved 2026-07-20. Next: implementation plan via writing-plans.
