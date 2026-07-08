# Link Review Triage — Steps 1 & 1.5 Design

**Date:** 2026-07-07
**Status:** Approved design, pending spec review
**Scope:** Steps 1 and 1.5 of `utils/Link Check & Review Process.md`
**Related:** `utils/link_checker.py`, `utils/Link Check & Review Process.md`

---

## Purpose

Produce a single **review spreadsheet** that classifies every external link on the
site so a human can make Step 1 (is it broken, and how?) and Step 1.5 (is it a
bulk-delete candidate?) decisions before any content is modified.

This build **stops at producing the spreadsheet.** No content is mutated. The
actual removal/unlinking of links is a separate, later, sheet-driven step,
explicitly out of scope here.

## Background & feasibility findings

The existing `link_checker.py` already performs most of Step 1 *detection*
(`extract` → `check` → `wayback` → `replace`). A prior run on this branch already
applied ~1,786 Wayback replacements (see git history), so the pipeline must be
**re-baselined against current content** before classification.

The planning doc defines four "Broken" categories. Their automatability differs
sharply, because two of them return a normal `200 OK`:

| Doc category | Description | Automatable? | Signal available |
|---|---|---|---|
| **A** — doesn't deliver | dead host / 404 / timeout | **Yes, reliably** | 404, CONN_ERROR, TIMEOUT, 5xx, SSL, 410 (~1,450 refs in last run) |
| **C** — wrong site (rebrand/hijack) | skype→teams, wallwisher→padlet | **Flag only** | substantive domain redirect + suspicious `<title>` keywords |
| **B** — right site, wrong page | resource moved to a new URL | **Mostly no** | returns 200; only soft-404s (title says "not found") are catchable |
| **D** — right site, defunct project | loads but doesn't function | **No** | returns 200; purely subjective |

**Consequence:** automated Step 1 produces a *triage*, not a verdict. B and D are
surfaced as `needs-human`, not decided by the tool.

Two ambiguous-status problems must be handled to keep false positives out of the
sheet (last run counts):

- **403 Forbidden (584 refs):** many are bot-blocks (WAF rejecting our
  User-Agent), not dead links. **Decision:** re-verify with a browser-like
  User-Agent before classifying.
- **Redirected to different domain (792 refs):** most are benign
  (http→https, www, trailing-slash, query-only). **Decision:** filter benign
  redirects out of the Broken-C candidate set.

Step 1.5 bulk-delete detection requires **document context** the current tool does
not capture (only URL + link text are recorded today). Bucket feasibility:

- **Booksellers/promo** — domain match; high confidence. Last run: amazon (70),
  books.google (104), abebooks (1).
- **Bibliography / Further Reading / References** — detectable by tracking the
  nearest preceding markdown heading. Content uses `## For Further Reading`
  (137 files) and `## Bibliography` (5 files); there are **no** `***`/`___`
  dividers, so the doc's "below the line divider" concept maps to headings here.
- **Photo/source captions** — no clean markdown structure; **low-confidence flag
  only**, not an auto-bucket.

## Decisions (from brainstorming)

1. **Buckets to detect:** all three — booksellers, bibliography sections, and
   captions (captions low-confidence).
2. **Bulk-delete precondition:** *in-bucket alone* qualifies a link as a
   candidate, regardless of HTTP status; the sheet shows the status so the human
   decides. (Lets the team prune live purchase links that don't serve the
   mission.)
3. **Ambiguous statuses:** re-verify 403s with a browser-like User-Agent, and
   filter benign redirects, before classifying.
4. **Output:** both `link_review_master.csv` (canonical, git-friendly) and an
   `.xlsx` (frozen header + autofilter) for humans to work in.

## Approach

Extend `utils/link_checker.py` with new subcommands rather than adding a separate
script — it already owns the extract/check/wayback plumbing and CSV conventions,
and the team already runs it.

## Pipeline

Four stages, building on existing commands.

### Stage 1 — Enrich `extract` with document context

For each external link, additionally record:

- `doc_heading` — text of the nearest preceding markdown heading (`^#+`)
- `in_bibliography` — boolean; true when `doc_heading` matches a curated list
  (*For Further Reading, Bibliography, References, Works Cited, Further
  Resources*). **Whole-heading match** against the list, so `## Sources of Unity`
  does not false-positive.
- `in_caption` — **low-confidence** boolean; true when the link sits on a line
  containing an image (`![...]`) or the link text looks like a citation
  ("Library of Congress", "Courtesy", "Source:", a bare year).
- `link_kind` — `hyperlink` (`[text](url)` / `<a href>`) vs `bare_url`; needed
  later to choose unlink-vs-delete.

Existing inventory columns are preserved.

### Stage 2 — `recheck` ambiguous statuses

- Re-request all `403` (and other block-looking) URLs with a browser-like
  User-Agent + `Accept`/`Accept-Language` headers; update `http_status`.
- Compute `redirect_kind` for redirects: `benign` (scheme/www/slash/query-only
  normalization) vs `substantive` (real domain change). Only `substantive`
  feeds the Broken-C candidate set.

Re-check is resumable and rate-limited, matching the existing `check` pattern.

### Stage 3 — `classify` (pure post-processing, no network)

Joins enriched inventory + check results + wayback results into the master rows.
Derived columns:

- `broken_category` — `A` (reliably dead), `C-candidate` (substantive domain
  change / suspicious title), `B?` (soft-404), `live` (clean 200),
  `needs-human` (200 but possibly B/D — tool cannot decide), `blocked-unknown`
  (still 403 after re-check).
- `bucket` — `bookseller` | `bibliography` | `caption_maybe` | `none`.
- `bulk_delete_candidate` — boolean; true when `bucket != none` (per decision 2).
- `confidence` — `high` | `medium` | `low`.
- `wayback_url`, `wayback_status` — joined from existing wayback data.
- `suggested_action` — hint only: `bulk-unlink` | `salvage-wayback` |
  `needs-subjective-review` | `ok`. The human decides; this is not executed.

### Stage 4 — Output

- `utils/link_review_master.csv` — one row per link reference, all columns above
  plus the existing identity columns (`section`, `page_title`, `page_url`,
  `source_file`, `link_url`, `link_text`, `http_status`, `final_url`,
  `remote_title`).
- `utils/link_review_master.xlsx` — same data, frozen header row + autofilter,
  sensible column widths. (Adds `openpyxl` to the script's inline deps.)

## Master sheet columns (final)

```
section, page_title, page_url, source_file,
link_url, link_text, link_kind,
doc_heading, in_bibliography, in_caption,
http_status, final_url, redirect_kind, remote_title,
broken_category, bucket, bulk_delete_candidate,
confidence, suggested_action,
wayback_url, wayback_status
```

## Out of scope

- Any content mutation / actual link removal (separate later step, sheet-driven).
- Automated verdicts for Broken **B** and **D** (surfaced as `needs-human`).
- Caption detection beyond a low-confidence flag.
- Steps 2–4 of the planning doc (subjective review, salvage decisions, enactment).

## Testing / verification

No automated suite in this repo (per AGENTS.md). Verify by:

1. Run `extract` → confirm new context columns populate on known files
   (e.g., a file with `## For Further Reading` flags `in_bibliography`).
2. Spot-check `recheck`: a known bot-blocked 403 resolves to 200 with a
   browser UA; a benign http→https redirect classifies `redirect_kind=benign`.
3. Confirm `classify` bucket counts roughly match the feasibility numbers
   (amazon ~70, books.google ~104, bibliography ~140 files).
4. Open the `.xlsx`, confirm autofilter + frozen header, filter by
   `bulk_delete_candidate=TRUE` and by `broken_category`.
5. Manually audit ~20 rows across categories to confirm labels are sane before
   the team relies on the sheet.

## Status & Handoff (as of 2026-07-07)

**Built and merged to branch `fix/dead-links`** (commits `41648d7d`..`8ab7853a`):
extract-with-context, `recheck`, `classify`, and xlsx output, with a 12-test
unit suite. All four plan tasks passed spec + quality review; the whole-branch
review returned "ready to finish, no blockers."

**Deliverable produced:** `utils/link_review_master.csv` / `.xlsx`, 5,913 links
with full HTTP coverage. Category counts: live 3,444; A (dead) 1,218;
blocked-unknown 655; C-candidate 500; B? 54; needs-human 42. 929 bulk-delete
candidates; 1,800 dead links have a Wayback snapshot.

**To regenerate the sheet** (full run; the `check` phase is slow — it makes
~5,300 live HTTP requests and many citation/bare URLs hit the 15s timeout, so
budget 30–60+ min):
```
uv run utils/link_checker.py extract          # only if content changed
uv run utils/link_checker.py check --resume
uv run utils/link_checker.py recheck
uv run utils/link_checker.py wayback --resume
uv run utils/link_checker.py classify
```

**What is intentionally NOT built yet (the next session's work):**
- There is **no `apply`/removal command** that acts on the sheet. Steps 2–4 of
  `utils/Link Check & Review Process.md` (remove/salvage decisions and
  enactment) are still manual/team-driven. A future `apply` step should be
  sheet-driven: read a human-approved `decision` column and unlink/replace
  accordingly, dry-run first, and — like this build — never touch content until
  approved. (The existing `replace` subcommand only swaps dead links for Wayback
  URLs; it is not the general apply step.)
- `broken_category` B and D (per the process doc) are surfaced as
  `needs-human`/`live`, not auto-decided — this is by design; they require the
  subjective review.

**Known deferred item (out of scope here):** `check_url` computes its
`redirect_domain_changed` flag with `.lstrip("www.")`, which strips a leading
character *set* (any of `w`/`.`), not the `www.` prefix. `classify` does NOT
consume that column — it recomputes `redirect_kind` via `removeprefix("www.")`
— so the master sheet is unaffected. Fix `check_url` if that column is ever
used directly.

**Bare-URL capture note:** `extract` now also captures written-out URLs (not
just `[text](url)` / `<a>`), tagged `link_kind=bare_url`. This raised the
inventory from ~4,549 to 5,913 refs. A partial/interrupted `check` leaves some
rows with an empty `http_status`; `classify` labels those `needs-human` and
prints a coverage warning — run a full `check` before relying on the sheet.
