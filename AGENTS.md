# AGENTS.md

> For feature specifications, business rules, and domain models, see [SPEC.md](./SPEC.md).

---

## Table of Contents

- [Project Overview](#project-overview)
- [Tech Stack](#tech-stack)
  - [Package Management](#package-management)
  - [Frontend](#frontend)
- [Project Initialization](#project-initialization)
- [Project Structure](#project-structure)
- [Architecture](#architecture)
- [Development Workflow](#development-workflow)
  - [Version Control](#version-control)
  - [Serving the Application](#serving-the-application)
  - [Testing Approach](#testing-approach)
- [Best Practices & Key Conventions](#best-practices--key-conventions)
- [Notes for AI Agents](#notes-for-ai-agents)

---

## Project Overview

Teachinghistory.org is a K–12 history education resource site created by the Roy Rosenzweig Center for History and New Media (CHNM) at George Mason University, with funding from the U.S. Department of Education. The site provides lesson plans, teaching guides, primary source reviews, best practices, and historian Q&A resources for elementary, middle, and high school teachers.

This repository is a full rebuild of the frontend as a Hugo static site, migrating from a legacy Drupal CMS. The design is driven by a comprehensive spec in [DESIGN.md](./DESIGN.md). Content was exported from Drupal as Markdown files with frontmatter preserving original URLs and metadata.

---

## Tech Stack

- **Static site generator:** Hugo (v0.154.5+)
- **CSS framework:** Tailwind CSS v3 with PostCSS pipeline
- **Fonts:** Google Fonts — Lora (headings), Roboto Slab (body)
- **Task runner:** [just](https://github.com/casey/just) (justfile in repo root)
- **No backend / no database** — this is a fully static site

### Package Management

- **Package manager:** npm
- **Node.js:** v18+
- **Dependencies are dev-only** (Tailwind, PostCSS, autoprefixer, postcss-cli)
- **package.json** lives in `teachinghistory-website/`
- **Lock file:** committed
- **Key scripts:**
  - `npm run dev` — starts Hugo dev server with live reload
  - `npm run build` — production build with minification

### Frontend

- **Hugo** generates all HTML from Go templates in `layouts/`
- **Tailwind CSS v3** via PostCSS, processed through Hugo Pipes (not a separate build step)
- **No JavaScript framework** — vanilla JS only where needed (carousel scroll buttons)
- **CSS custom properties** defined in `assets/css/main.css` as design tokens
- **Google Fonts** loaded via `<link>` tags in `baseof.html`
- **Tailwind config** extends colors (orange, yellow, green, pale-blue with DEFAULT + tint variants), fonts (heading: Lora, body: Roboto Slab), and the standard type scale

---

## Project Initialization

1. **Prerequisites:**
   - Hugo v0.154.5+ (extended edition for PostCSS support)
   - Node.js 18+
   - npm
   - [just](https://github.com/casey/just) command runner (optional but recommended)

2. **Install dependencies:**
   ```bash
   cd teachinghistory-website
   npm install
   ```

3. **Start dev server:**
   ```bash
   just serve
   # or: cd teachinghistory-website && hugo server -D --navigateToChanged
   ```

4. **Access the site:** `http://localhost:1313`

5. **Rebuild Tailwind CSS** (if classes aren't appearing):
   ```bash
   just css
   ```
   This clears Hugo's cached `resources/_gen/` and rebuilds.

---

## Project Structure

```
teachinghistory-hugo/
├── DESIGN.md                          # Master design specification
├── AGENTS.md                          # This file — developer/AI context
├── SPEC.md                            # Product specification
├── justfile                           # Task runner commands
├── th_logo.png                        # Horizontal logo source
├── th_logo_stacked.png                # Stacked logo source
└── teachinghistory-website/           # Hugo site root
    ├── hugo.toml                      # Hugo configuration
    ├── package.json                   # npm dependencies (Tailwind, PostCSS)
    ├── postcss.config.js              # PostCSS config (Tailwind + autoprefixer)
    ├── tailwind.config.js             # Tailwind theme extensions
    ├── assets/
    │   └── css/
    │       └── main.css               # Tailwind directives + CSS custom properties
    ├── content/                       # Markdown content (migrated from Drupal)
    │   ├── _index.md                  # Homepage
    │   ├── teaching-materials/        # Orange section
    │   │   ├── _index.md
    │   │   ├── lesson-plan-reviews/
    │   │   ├── teaching-guides/
    │   │   ├── english-language-learners/
    │   │   └── ask-a-master-teacher/
    │   ├── history-content/           # Yellow section
    │   │   ├── _index.md
    │   │   ├── website-reviews/
    │   │   ├── beyond-the-textbook/
    │   │   ├── quiz/
    │   │   ├── national-resources/
    │   │   └── ask-a-historian/
    │   ├── best-practices/            # Green section
    │   │   ├── _index.md
    │   │   ├── examples-of-historical-thinking/
    │   │   ├── teaching-in-action/
    │   │   ├── teaching-with-textbooks/
    │   │   └── using-primary-sources/
    │   ├── digital-classroom/         # Pale-blue section
    │   │   ├── _index.md
    │   │   ├── ask-a-digital-historian/
    │   │   ├── beyond-the-chalkboard/
    │   │   └── tech-for-teachers/
    │   └── ...                        # about, blog, grade-level, etc.
    ├── layouts/
    │   ├── _default/
    │   │   ├── baseof.html            # Base template (fonts, CSS, nav, footer)
    │   │   ├── list.html              # Default list template
    │   │   ├── single.html            # Default single-page template
    │   │   └── section-index.html     # Carousel index layout (used by main sections)
    │   ├── index.html                 # Homepage template
    │   └── partials/
    │       ├── navbar.html            # Fixed top navigation bar
    │       ├── footer.html            # Footer with Quick Links bar
    │       ├── page-hero.html         # Section accent-color hero banner
    │       ├── section-color.html     # Returns accent color name for a section
    │       ├── content-card.html      # 250px content card component
    │       ├── horizontal-carousel.html # Scrollable card carousel row
    │       └── arrow-button.html      # Rounded pill CTA button
    └── static/
        └── images/                    # Logo files and static assets
```

### Key conventions

- **One component per partial file** in `layouts/partials/`
- **Content uses nested directories** matching URL hierarchy (e.g., `content/teaching-materials/lesson-plan-reviews/`)
- **`url` frontmatter** in content files preserves original Drupal URLs
- **`_index.md`** files define section metadata (title, description, weight, layout)
- **`layout: section-index`** in parent `_index.md` triggers the carousel layout
- **Weight** in `_index.md` controls subsection ordering within carousels

---

## Architecture

Hugo builds static HTML at build time. There is no server-side runtime.

```
Google Fonts CDN ──→ Browser
                       ↓
                   baseof.html
                   ├── navbar.html
                   ├── page-hero.html
                   ├── [page content]
                   │   └── section-index.html / list.html / single.html
                   │       └── horizontal-carousel.html
                   │           └── content-card.html + arrow-button.html
                   └── footer.html
```

- **CSS pipeline:** `assets/css/main.css` → PostCSS (Tailwind + autoprefixer) → Hugo Pipes → minified/fingerprinted in production
- **Section color mapping** is handled by `section-color.html` partial: teaching-materials→orange, history-content→yellow, best-practices→green, everything else→pale-blue
- **Carousel scrolling** uses vanilla JS `scrollBy()` on button click — no external JS dependencies

---

## Development Workflow

### Version Control

- **Branching:** Feature branches off `main` (e.g., `feat/design-rebuild`)
- **Branch naming:** `feat/`, `fix/`, `docs/`, `refactor/` prefixes
- **Commit format:** Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, etc.)
- **Merge strategy:** Merge commits to `main`
- **Current work branch:** `feat/design-rebuild` (via `preview` base)

### Serving the Application

**Development:**
```bash
just serve
# → http://localhost:1313 with live reload
```

**Production build:**
```bash
just build
# Output: teachinghistory-website/public/
```

**Rebuild CSS** (clears Hugo's asset cache):
```bash
just css
```

**Clean all generated files:**
```bash
just clean
```

### Testing Approach

No automated test suite currently. Verify changes by:
1. Running `just serve` and visually inspecting in the browser
2. Running `just check` for Hugo warnings (unused templates, broken paths)
3. Running `just build` to confirm production build succeeds

---

## Best Practices & Key Conventions

**Component architecture:**
- Each UI component is a separate partial in `layouts/partials/`
- Partials accept parameters via Hugo `dict` — document expected params in a comment block at top of file
- Use `section-color.html` to derive accent colors rather than hardcoding

**Naming conventions:**
- Partial files: `kebab-case.html`
- CSS classes: Tailwind utility classes (no custom class names except design tokens)
- Content directories: `kebab-case` matching URL path segments

**Tailwind usage:**
- Extend the theme in `tailwind.config.js` — don't use arbitrary values for project colors/fonts
- Design tokens are defined as CSS custom properties in `main.css` AND as Tailwind theme extensions
- If a new Tailwind class isn't appearing, run `just css` to clear the asset cache

**Content structure:**
- All content files have `url` frontmatter preserving original Drupal paths
- Section `_index.md` files must have `title`, `description`, and `weight`
- Parent sections use `layout: section-index` to get the carousel page

**HTML/accessibility:**
- Semantic HTML elements (`<nav>`, `<main>`, `<footer>`, `<article>`)
- `aria-label` and `aria-current` attributes on navigation
- All images should have `alt` attributes

---

## Notes for AI Agents

**Important context:**
- All design decisions come from [DESIGN.md](./DESIGN.md) — do not invent layout details, colors, or component behavior
- The site is a migration from Drupal — content files contain legacy frontmatter fields that should be preserved
- The "Ask a Historian" feature has been dropped — do not implement AskAHistorianBanner
- Nav active state always uses orange (`text-orange`), not per-section accent colors

**When making changes:**
- Read existing code before modifying — understand the partial's parameter interface
- Follow the one-component-per-file pattern for new partials
- Use `just css` after adding new Tailwind classes if they don't appear
- Use `just serve` to verify changes visually
- Commit with conventional commit format

**Font substitution:**
- DESIGN.md may reference "Quincy CF" — use **Lora** (Google Fonts) instead
- Body font is **Roboto Slab** (Google Fonts)

**What to avoid:**
- Don't add JavaScript frameworks or build tools — keep it vanilla JS + Hugo Pipes
- Don't create new CSS class names — use Tailwind utilities
- Don't restructure content directories without understanding the `url` frontmatter mapping
- Don't modify `url` frontmatter in content files (preserves SEO/link continuity from Drupal)

**Build phases** (from DESIGN.md, in progress):
- Phases 1–4 complete: design tokens, global components, carousel layout, content restructure
- Phases 5–10 remaining: homepage, detail page layouts, grade-level pages, about/staff, bio modal, lesson format scale

---

*Last Updated: 2026-03-10*
*This document is maintained for AI agent context and onboarding.*
