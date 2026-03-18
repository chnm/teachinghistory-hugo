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

## Design & Layout

- [ ] **Responsive / mobile design.** Desktop layouts are implemented but no mobile breakpoints exist. Confirm with design team and implement.
- [ ] **Quiz section.** Currently uses default templates. May need its own interactive layout if quizzes should be functional rather than static content.
- [ ] **Blog section layout.** Blog content exists but isn't referenced in the design spec. Decide if it needs a dedicated layout.

## Infrastructure

- [ ] **Set up CI/CD deployment.** Triggers configured for `main` and `preview` branches but deployment target needs to be configured.
- [ ] **Consider Git LFS or server-side hosting for large media.** The 16 BTC video files are currently in the repo (~485 MB). The additional ~253 best-practices videos would add several more GB. Consider moving all video files to server-side storage.

---

*Last updated: 2026-03-11*
