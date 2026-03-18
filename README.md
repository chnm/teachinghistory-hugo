# TeachingHistory.org

A K-12 history education resource site built with [Hugo](https://gohugo.io/) and [Tailwind CSS](https://tailwindcss.com/), created by the [Roy Rosenzweig Center for History and New Media](https://rrchnm.org/) at George Mason University with funding from the U.S. Department of Education.

This repository is a full rebuild of the site, migrated from a legacy Drupal CMS. It contains ~9,600 content pages covering lesson plans, teaching guides, primary source reviews, best practices, and more.

## Quick Start

**Prerequisites:** Hugo v0.154.5+ (extended), Node.js 18+, [just](https://github.com/casey/just)

```bash
cd teachinghistory-website && npm install   # one-time setup
just serve                                  # dev server at localhost:1313
```

## Commands

| Command       | Description                                      |
|---------------|--------------------------------------------------|
| `just serve`  | Dev server with hot reload (includes drafts)     |
| `just build`  | Production build (minified) to `public/`         |
| `just css`    | Force Tailwind rebuild (clears asset cache)      |
| `just clean`  | Remove `public/` and `resources/_gen/`           |
| `just check`  | Hugo warnings: unused templates, broken paths    |

## Project Structure

```text
teachinghistory-hugo/
├── teachinghistory-website/    # Hugo site root
│   ├── assets/css/main.css     # Tailwind + design tokens
│   ├── content/                # ~9,600 Markdown content files
│   ├── layouts/                # Hugo templates and partials
│   ├── static/                 # Images, video files, media
│   └── data/                   # Staff YAML data
├── docs/                       # Project documentation
│   ├── DESIGN_SPEC.md          # Visual design specification
│   ├── architecture.md         # Technical architecture
│   ├── content.md              # Content management guide
│   ├── staff.md                # Staff data management
│   └── todo.md                 # Action items and known issues
├── utils/                      # One-time Drupal conversion scripts
├── AGENTS.md                   # Developer/AI agent context
├── SPEC.md                     # Product specification
└── CLAUDE.md                   # Claude Code instructions
```

## Content Sections

| Section              | Color  | Subsections                                                              |
|----------------------|--------|--------------------------------------------------------------------------|
| Teaching Materials   | Orange | Lesson Plan Reviews, Teaching Guides, ELL, Ask a Master Teacher          |
| History Content      | Yellow | Website Reviews, Beyond the Textbook, Quiz, National Resources           |
| Best Practices       | Green  | Historical Thinking, Teaching in Action, Textbooks, Primary Sources      |
| Digital Classroom    | Blue   | Ask a Digital Historian, Beyond the Chalkboard, Tech for Teachers        |

## Documentation

- **[AGENTS.md](AGENTS.md)** - Tech stack, project structure, development workflow
- **[SPEC.md](SPEC.md)** - Business rules, features, user flows
- **[docs/DESIGN_SPEC.md](docs/DESIGN_SPEC.md)** - Design tokens, component specs, page layouts
- **[docs/todo.md](docs/todo.md)** - Outstanding action items
