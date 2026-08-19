# Todo

Action items and known issues for the TeachingHistory.org Hugo rebuild.

---

## Video Files

- [ ] **Download ~253 MP4 video files for Best Practices pages.** ~75 pages in examples-of-historical-thinking, teaching-in-action, and using-primary-sources reference video files at `/files/media/video/`. Thumbnails are already in `static/files/media/video/thumbs/` but the MP4s themselves have not been downloaded. These can be copied directly to the server post-deploy rather than committing to git (they'd be several GB). Source: live Drupal site at `teachinghistory.org/sites/default/files/media/video/`.
- [ ] **Convert Best Practices video pages to use `video-player.html` partial.** Currently these pages use inline markdown (thumbnail image linking to MP4). The Beyond the Chalkboard pages in digital-classroom already use the `videos:` frontmatter + `video-player.html` partial for a polished multi-video UI. Apply the same treatment to best-practices pages for consistency.
- [ ] **Check 2 teaching-materials and ~13 history-content pages with incidental video references.** These have body text linking to video files — verify they work once MP4s are on the server.

## Content

- [ ] **Review misc legacy content sections.** Directories like `annual-report/`, `press-release/`, `enews/`, `blog/` exist in `content/` but don't have dedicated layouts. Decide whether to build layouts or leave them on the default `list.html`/`single.html`.
- [ ] **Audit History Content topic/time period data.** The History Content subsection list pages have Topic and Time Period dropdown filters, but content doesn't have structured frontmatter for these — the dropdowns filter against combined title + summary + keywords text. Consider adding structured `topic` and `time_period` fields to content if more precise filtering is needed.
- [ ] **Review `keywords` field formatting.** Some history-content pages have `keywords` as a string, others as an array. The template handles both, but normalizing to one format would be cleaner.

## Link Review & Cleanup

The automated triage (Steps 1 & 1.5 of `utils/Link Check & Review Process.md`)
is done. `utils/link_checker.py` produces `utils/link_review_master.xlsx` /
`.csv` — 5,913 external links classified by broken-ness (`broken_category`),
bulk-delete bucket (`bucket`, `bulk_delete_candidate`), `confidence`, and a
suggested action. The 500 `C-candidate` (moved-site) links are further split
by `rebrand_verdict`: 147 probably-broken / 293 probably-fine / 60
needs-human, using `final_is_homepage` and `history_signal` as supporting
columns. A `pages` subcommand aggregates the master sheet into
`utils/link_review_pages.xlsx` / `.csv` — one row per page with a
`suggested_page_action` (delete-page-candidate / salvage-wayback /
fix-links-only) for bulk page-level decisions. Full design + handoff:
`docs/superpowers/specs/2026-07-07-link-review-triage-design.md` and
`docs/superpowers/specs/2026-07-20-rebrand-triage-and-page-sheet-design.md`.
These review sheets and intermediate CSVs are local, git-ignored artifacts.

- [ ] **Team review + sign-off on the sheet.** Start from
  `link_review_pages.xlsx` for page-delete calls (`suggested_page_action`),
  and the master sheet for link-level calls. Both xlsx files have a `decision`
  dropdown column: pages sheet (delete-page / salvage-wayback / fix-links /
  keep), master sheet (remove / update-to-final-url / salvage-wayback /
  salvage-new-link / keep). Start with
  `bulk_delete_candidate = TRUE` (929 links: booksellers, bibliography,
  captions), then `broken_category = A` with a Wayback snapshot (1,800 dead
  links are archived), then `C-candidate` (500 moved sites). No content changes
  until the sheet is approved.
- [ ] **Build the sheet-driven `apply` step.** No command yet acts on approved
  decisions (unlink text / replace with Wayback or new URL). Must be dry-run
  first and never mutate content without approval. See the design doc's
  "Status & Handoff" section.
- [ ] **Subjective review (Steps 2–4).** `needs-human` (42) and
  `blocked-unknown` (655) rows, plus salvage-vs-remove calls, need human
  judgment per the process guide.

## Cleanup (eventually — after link review wraps and migration is final)

Nothing here is urgent; do not delete anything while the link review is in
flight. Listed so we don't lose track:

- [x] **Remove link-checker outputs from git.** Current and legacy review CSVs
  and workbooks are generated locally and ignored by git.
- [ ] **Drop `utils/content/` from git.** 9,604 tracked files (~55 MB) of raw
  one-time Drupal conversion output, superseded by
  `teachinghistory-website/content/`. Remove once the site content is
  considered final (history stays in git if we ever need it).
- [ ] **Delete untracked local conversion artifacts.** `utils/content-new/`
  (~56 MB), `utils/th_db.sql` (873 MB, gitignored), `utils/conversion.log` —
  local-only; safe to delete from disk whenever the conversion is truly done.
- [ ] **Archive or remove one-time conversion scripts.** `drupal_to_hugo.py`,
  `extract_duration.py`, `extract_grade_levels.py`, `fetch_images.py`,
  `fix_btc_transcripts.py`, `merge_btt_pairs.py`, `merge_content.py`,
  `reprocess_content.py` (plus `CONVERSION_SUMMARY.md` / `DEVNOTES.md` and the
  conversion sections of `utils/CLAUDE.md`). Post-launch, either delete or move
  to a `utils/conversion/` subfolder so `utils/` is just the link tooling.
- [ ] **Archive link-review decisions post-apply.** Once the team's decisions
  are applied and verified, archive the local master/pages sheets outside the
  repository if they need to be retained as a project record.

## Design & Layout

- [ ] **Responsive / mobile design.** Desktop layouts are implemented but no mobile breakpoints exist. Confirm with design team and implement.
- [ ] **Quiz section.** Currently uses default templates. May need its own interactive layout if quizzes should be functional rather than static content.
- [ ] **Blog section layout.** Blog content exists but isn't referenced in the design spec. Decide if it needs a dedicated layout.

## Infrastructure

- [x] **Set up CI/CD deployment.** Triggers configured for `main` and `preview` branches but deployment target needs to be configured.
- [ ] **Consider Git LFS or server-side hosting for large media.** The 16 BTC video files are currently in the repo (~485 MB). The additional ~253 best-practices videos would add several more GB. Consider moving all video files to server-side storage.

---

*Last updated: 2026-07-21*
