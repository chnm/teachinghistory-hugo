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
uv run utils/link_checker.py extract          # Build link inventory from content/
uv run utils/link_checker.py check --resume   # Check HTTP status of each URL
uv run utils/link_checker.py wayback --resume # Look up Wayback Machine snapshots for dead links
```

Outputs CSVs in `utils/`: `link_inventory.csv`, `link_results.csv`, `link_review.csv`, `link_review_priority.csv`, `link_wayback.csv`.

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
- `AGENTS.md` — detailed tech stack, project structure, development workflow
- `SPEC.md` — business rules, features, user flows
- `docs/todo.md` — human-readable action items and known issues
- `utils/CLAUDE.md` — Drupal conversion script details
