# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Teachinghistory.org — a K–12 history education resource site (CHNM / George Mason University). This repo is a Drupal-to-Hugo migration: ~9,600 content files converted from a Drupal SQL database, now being rebuilt as a static Hugo site with a custom Tailwind CSS theme.

The Hugo site lives in `teachinghistory-website/`. The `utils/` directory contains the one-time Drupal conversion scripts (see `utils/CLAUDE.md` for those details) and a link checker for auditing external URLs.

## Build Commands

All commands use [just](https://github.com/casey/just) from the repo root:

```bash
just serve         # Dev server at localhost:1313 (hot reload, includes drafts)
just build         # Production build (minified) → teachinghistory-website/public/
just css           # Force Tailwind rebuild (clears resources/_gen/ cache)
just clean         # Remove public/ and resources/_gen/
just check         # Hugo warnings: unused templates, broken paths
```

npm scripts exist in `teachinghistory-website/package.json` but Hugo Pipes handles PostCSS internally — you typically only need `npm install` once for the Tailwind/PostCSS devDependencies.

### External Link Checker

`utils/link_checker.py` audits external links across all content files. Run with `uv`:

```bash
uv run utils/link_checker.py extract          # Build link inventory (with document context)
uv run utils/link_checker.py check --resume   # Check HTTP status of each URL
uv run utils/link_checker.py recheck          # Re-verify 403s with a browser user-agent
uv run utils/link_checker.py wayback --resume # Look up Wayback snapshots for dead links
uv run utils/link_checker.py classify         # Build the master review sheet (CSV + XLSX)
uv run utils/link_checker.py pages            # Aggregate master sheet into a per-page review sheet
```

Outputs CSVs in `utils/`: `link_inventory.csv`, `link_results.csv`, `link_wayback.csv`, `link_review_master.csv`, `link_review_pages.csv`. The `classify` step also writes `link_review_master.xlsx` (frozen header row + autofilter) — the human-friendly sheet for manual triage. The `pages` step writes `link_review_pages.xlsx` the same way, for bulk page-level (delete/salvage/keep) decisions. Both xlsx sheets end with a blank `decision` dropdown column where the team records their calls; the CSVs never contain decisions.

### Legacy URL Redirects (Drupal → Hugo → Caddy)

> **Full guide: [`docs/REDIRECTS.md`](docs/REDIRECTS.md)** — design, runbook, verification, performance, CMS-agnostic reuse, and deployment. This section is the summary.

Hugo serves **native** URLs (derived from file location); the **web server (Caddy)** owns all 301 redirects from old Drupal URLs. The map is deterministic and built from the Hugo content itself — no Drupal DB / LAMP artifacts required.

Native URLs are clean slugs with **no** node id: content files are named `{slug}.md` (the `-{drupal_nid}` suffix was stripped by `utils/strip_nid_slugs.py`), so `/history-content/website-reviews/statistics-in-schools/`, not `.../statistics-in-schools-25863/`. The nid is kept only on the ~38 files whose slug would otherwise collide (e.g. Beyond-the-Textbook pairs), and always stays in `drupal_nid` frontmatter for provenance + `/node/{nid}` redirects.

Legacy Drupal paths live in each page's `aliases:` frontmatter as **data only**. `disableAliases = true` (hugo.toml) means Hugo writes **no** alias stub HTML — Caddy is the sole redirect authority. The home page emits `/redirects.json` (via `layouts/index.redirects.json`) listing every page's native URL plus its legacy paths (the `aliases:` values **and** the synthesized `/node/{drupal_nid}` path). That manifest is the source of truth for the pipeline.

**Preserving redirects when pages merge/move:** because each redirect is derived from the surviving page's `aliases:` + `drupal_nid:`, whenever two pages become one you must move the retired page's old URLs onto the survivor — add both its path-alias **and** `/node/{its_nid}` to the survivor's `aliases:` — or those old URLs 404. `utils/finalize_btt_merge.py` does this for the Beyond-the-Textbook Part 1/Part 2 merge (each topic's two nids both redirect to the single merged page).

```bash
uv run utils/relocate_urls.py --apply                 # One-time: url: -> aliases: (idempotent)
uv run utils/strip_nid_slugs.py --apply               # One-time: drop -{nid} from filenames (idempotent)
uv run utils/finalize_btt_merge.py --apply            # One-time: retire BTT Part 1 drafts, keep their redirects
just build                                             # Hugo emits public/redirects.json
uv run utils/redirect_mapper.py build                 # Manifest -> utils/redirect_map.csv
uv run utils/redirect_mapper.py reconcile             # Merge old_urls.csv + parent-section fallback
uv run utils/redirect_mapper.py generate              # -> teachinghistory-website/static/redirects.caddy (committed; Hugo copies to public/)
uv run utils/redirect_mapper.py crosscheck --old-site https://teachinghistory.org  # live oracle (QA)
uv run utils/redirect_mapper.py verify --target http://localhost:8080              # 301->200, no loops
uv run utils/redirect_mapper.py parity --old-site https://teachinghistory.org --target http://localhost:8080  # source+target both 200
```

`redirects.caddy` is a `map {path} {redirect_target}` block imported by the `Dockerfile` Caddy config; it emits both trailing-slash variants, skips self-redirect loops, and resolves conflicts deterministically. It is generated into `teachinghistory-website/static/`, so Hugo copies it to `public/redirects.caddy` (shipping it in the build/release artifact); the container imports it from `/srv/redirects.caddy`. The `static/` copy is **committed** (CI only builds Hugo + `docker build`s it; the live-site crosscheck never runs in CI). `redirect_map.csv`/`old_urls.csv` are committed for auditing; `redirect_verify.csv`/`redirect_crosscheck.csv` are gitignored transient reports.

The pipeline is CMS-agnostic by design (pluggable map-source / identity-extractor / URL-enumerator seams in `redirect_mapper.py`), so it can be reused for other Omeka/Drupal/WordPress → Hugo migrations.

## Architecture

### CSS Pipeline

`assets/css/main.css` → PostCSS (Tailwind JIT + autoprefixer) → Hugo Pipes → minified/fingerprinted in production. CSS custom properties define design tokens; Tailwind config extends the same values. If a new Tailwind class doesn't appear, run `just css`.

### Template Hierarchy

`baseof.html` wraps all pages (loads Google Fonts, CSS, navbar, footer). Content templates:
- `index.html` — homepage
- `section-index.html` — carousel layout for main sections (triggered by `layout: section-index` in `_index.md`)
- `grade-level.html` — grade-filtered browsing pages (Elementary, Middle, High School)
- `list.html` — default list; section-specific `list.html` templates provide filterable subsection listings
- `single.html` — default detail page fallback
- Section-specific overrides live in `layouts/<section>/` (e.g., `layouts/digital-classroom/single.html`, `layouts/teaching-materials/list.html`)

### Component System

Each UI component is a Hugo partial in `layouts/partials/`. Partials receive params via `dict`:

```go
{{ partial "page-hero.html" (dict "title" .Title "color" $color) }}
```

The `section-color.html` partial maps section name → accent color (`"orange"`, `"yellow"`, `"green"`, `"pale-blue"`). Always use this partial rather than hardcoding colors.

The `video-player.html` partial renders a tabbed video player with transcript from frontmatter `videos` data (used by Beyond the Chalkboard pages in digital-classroom).

The `subsection-list.html` partial provides a 1/3-2/3 filterable listing layout for subsection pages, with a sticky search card in the left sidebar and a 2-column card grid on the right. Each section has its own search card partial (e.g., `search-teaching-materials.html`) with section-appropriate filter fields. Client-side vanilla JS handles keyword search and dropdown filtering.

### Content Structure

Four main sections, each with nested subsections:
- **teaching-materials/** (orange) — lesson-plan-reviews, teaching-guides, english-language-learners, ask-a-master-teacher
- **history-content/** (yellow) — website-reviews, beyond-the-textbook, quiz, national-resources, ask-a-historian
- **best-practices/** (green) — examples-of-historical-thinking, teaching-in-action, teaching-with-textbooks, using-primary-sources
- **digital-classroom/** (pale-blue) — ask-a-digital-historian, beyond-the-chalkboard, tech-for-teachers

Section index pages auto-discover subsections via `.Sections.ByWeight`. Subsection ordering is controlled by `weight` in `_index.md` frontmatter.

Content files have `url` frontmatter preserving original Drupal paths — do not modify these.

## Design Rules

All design decisions come from `docs/DESIGN_SPEC.md`. Do not invent layout details, colors, or component behavior.

- **Fonts:** Lora for headings (replaces "Quincy CF" from spec), Roboto Slab for body
- **Nav active state:** Always orange (`text-orange`), not per-section accent colors
- **Ask a Historian:** Feature has been dropped — do not implement
- **Carousel:** Arrow-button scroll only (vanilla JS `scrollBy()`), no drag/swipe, no JS frameworks

## Git Conventions

- Branch naming: `feat/`, `fix/`, `docs/`, `refactor/` prefixes
- Commit format: Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`)
- CI/CD triggers on pushes to `main` or `preview` branches for paths under `teachinghistory-website/`

## Related Docs

- `docs/DESIGN_SPEC.md` — visual design spec, component inventory, page specifications
- `docs/REDIRECTS.md` — legacy-URL redirect pipeline (Drupal → Hugo → Caddy): design, runbook, verification, performance, reuse
- `AGENTS.md` — detailed tech stack, project structure, development workflow
- `SPEC.md` — business rules, features, user flows
- `docs/todo.md` — human-readable action items and known issues
- `utils/CLAUDE.md` — Drupal conversion script details
