# Site Architecture

## Project structure

```
teachinghistory-hugo/
├── docs/                  # Documentation (not built by Hugo)
├── utils/                 # Migration and maintenance scripts
│   ├── fetch_images.py    # Download images from old Drupal site
│   ├── merge_btt_pairs.py # Merge Beyond the Textbook part 1+2 pages
│   └── ...
├── justfile               # Task runner commands
└── teachinghistory-website/
    ├── archetypes/        # Content scaffolding templates
    ├── assets/css/        # Tailwind CSS source
    ├── content/           # All site content (Markdown)
    ├── data/              # Structured data (staff.yaml)
    ├── layouts/           # Hugo templates
    │   ├── _default/      # Default layouts (single, section-index, list)
    │   ├── about/         # About section layouts (staff)
    │   ├── best-practices/# Best Practices section layout
    │   ├── history-content/# History Content section layout
    │   └── partials/      # Reusable template fragments
    ├── static/            # Static files (images, fonts)
    └── hugo.toml          # Site configuration
```

## Design tokens

Colors and fonts are defined in `assets/css/main.css` via Tailwind config:

| Token          | Value     | Usage                            |
|----------------|-----------|----------------------------------|
| `orange`       | `#F2A900` | Teaching Materials accent        |
| `yellow`       | `#FFCD00` | History Content accent           |
| `green`        | `#6CC24A` | Best Practices accent            |
| `pale-blue`    | `#9BB8D3` | Digital Classroom / About accent |
| `orange-tint`  | `#FEF5E0` | Teaching Materials background    |
| `yellow-tint`  | `#FFF9D6` | History Content background       |
| `green-tint`   | `#EFF8EB` | Best Practices background        |
| `pale-blue-tint`| `#EBF1F7`| Digital Classroom background     |

Fonts:
- **Headings**: Lora (serif) — `font-heading`
- **Body**: Roboto Slab (slab-serif) — `font-body`

## Layouts overview

### Section index pages (`section-index.html`)

Used by Teaching Materials, History Content, Best Practices, and Digital Classroom. Shows a tinted background with horizontal carousel rows, one per subsection. Each row has a left-side label with "View All" button and a scrollable card strip.

### Single page layouts

All single pages use a two-column layout (1/3 tinted sidebar + 2/3 white content area):

- **`_default/single.html`** — Minimal sidebar, page title + content
- **`best-practices/single.html`** — Sidebar with "At a Glance" card (summary) and "About the Author" card (photo + bio). Sticky sidebar on scroll.
- **`history-content/single.html`** — Sidebar with collapsible "What Textbooks/Historians/Sources Say" cards (for Beyond the Textbook pages) or "At a Glance" card. Related Topics section below content.

### Key partials

| Partial                  | Purpose                                          |
|--------------------------|--------------------------------------------------|
| `navbar.html`            | Fixed top navigation bar                         |
| `footer.html`            | Quick Links bar + 5-column footer                |
| `page-hero.html`         | Colored banner with section title pill            |
| `section-color.html`     | Maps section slug to accent color name           |
| `section-tint.html`      | Maps section slug to tint background class       |
| `content-card.html`      | Card component (image + title + summary)         |
| `horizontal-carousel.html`| Scrollable card row with navigation arrows      |
| `arrow-button.html`      | Colored pill button with arrow                   |

## Build commands

| Command             | Description                                |
|---------------------|--------------------------------------------|
| `just serve`        | Start dev server with live reload          |
| `just build`        | Production build with minification         |
| `just build-drafts` | Build including draft content              |
| `just css`          | Rebuild Tailwind (clears cached assets)    |
| `just clean`        | Remove generated files                     |
| `just new <path>`   | Create new content file from archetype     |
| `just check`        | Check for unused templates and path issues |
