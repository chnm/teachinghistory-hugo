# SPEC.md

> For technical implementation details, architecture, and developer documentation, see [AGENTS.md](./AGENTS.md).

---

## Table of Contents

- [Overview](#overview)
- [Users & Roles](#users--roles)
- [Business Rules](#business-rules)
- [Features](#features)
- [User Flows](#user-flows)
- [Out of Scope](#out-of-scope)
- [Open Questions](#open-questions)

---

## Overview

Teachinghistory.org is a free K–12 history education resource site created by the Roy Rosenzweig Center for History and New Media (CHNM) at George Mason University, funded by the U.S. Department of Education. The site serves as a curated library of lesson plans, teaching guides, primary source reviews, best practices, and historian Q&A resources for elementary, middle, and high school history teachers.

**Core value proposition:** A single, trustworthy destination where history teachers can find vetted, high-quality teaching resources organized by type, topic, and grade level.

**Target audience:** K–12 history and social studies teachers in U.S. schools.

**Primary goals:**
- Provide easy discovery of teaching resources across four main content areas
- Support grade-level browsing (elementary, middle, high school)
- Maintain accessibility and simplicity — no login required, all content freely available
- Preserve existing URL structure and SEO value from the legacy Drupal site

---

## Users & Roles

### Site Visitor (only role)

- **Description:** K–12 history or social studies teacher browsing for resources
- **Access level:** Full read access to all published content — no authentication required
- **Primary goals:** Find lesson plans, teaching guides, and best practices relevant to their grade level and subject area
- **Typical use cases:**
  - Browse a content section (e.g., Teaching Materials) to discover new resources
  - Navigate directly to a specific subsection (e.g., Lesson Plan Reviews)
  - Explore resources by grade level (Elementary, Middle, High School)
  - Read a detailed content page (lesson plan review, teaching guide, etc.)
  - Learn about the project team via the About Us page

There are no admin, editor, or authenticated user roles. Content is managed as static Markdown files in the repository.

---

## Business Rules

### Content Organization

- All content belongs to one of four top-level sections: **Teaching Materials**, **History Content**, **Best Practices**, or **Digital Classroom**
- Each top-level section contains named subsections (e.g., Teaching Materials → Lesson Plan Reviews, Teaching Guides, English Language Learners, Ask a Master Teacher)
- Subsections are ordered by `weight` in their `_index.md` frontmatter
- Every content page preserves its original Drupal URL via the `url` frontmatter field

### Section Color Mapping

| Section             | Accent Color | Hex       |
|---------------------|-------------|-----------|
| Teaching Materials  | Orange      | `#F26522` |
| History Content     | Yellow      | `#FFC20E` |
| Best Practices      | Green       | `#37A99C` |
| Digital Classroom   | Pale Blue   | `#DCEBF9` |
| About Us / Other    | Pale Blue   | `#DCEBF9` |

Each section's accent color is used in: PageHero background, "View All" buttons, and carousel UI elements.

### URL Structure

- Section index pages: `/{section}/` (e.g., `/teaching-materials/`)
- Content detail pages: preserved from Drupal via `url` frontmatter (e.g., `/teaching-materials/lesson-plan-reviews/abraham-lincoln-and-the-jews`)
- Grade-level pages: `/grade-level/elementary/`, `/grade-level/middle/`, `/grade-level/high/`
- About page: `/about/`

### Navigation

- Five navigation items in fixed order: About Us, Teaching Materials, History Content, Best Practices, Digital Classroom
- Active nav item is styled with orange text (`#F26522`) regardless of section

---

## Features

### Feature: Section Index Pages

**Description:**
Landing pages for each main content area (Teaching Materials, History Content, Best Practices, Digital Classroom) that display subsections as horizontal carousel rows.

**User Value:**
Lets teachers quickly scan across all resource categories within a section and preview individual items without navigating away.

**Functionality:**
- PageHero banner with section title in a black pill badge on accent-color background
- One HorizontalCarousel row per subsection, ordered by weight
- Each row has: heading, brief description, "View All →" pill button (left column), scrollable content cards (right)
- Left/right arrow buttons for scrolling cards
- Content cards show: title, image (or gray placeholder), truncated body text
- Entire card is clickable, linking to the detail page

**Edge Cases:**
- Subsection with no content pages: row still renders with heading but no cards
- Very long subsection descriptions: truncated in the left column

---

### Feature: Content Detail Pages

**Description:**
Individual resource pages showing the full content of a lesson plan review, teaching guide, article, etc.

**User Value:**
Provides the full text, images, and metadata for a single teaching resource.

**Functionality:**
- PageHero with section title
- Breadcrumb: subsection label (uppercase) + "← View all [Section]" link
- Layout varies by section type:
  - **Teaching Materials:** Two-column — left sidebar with "At a Glance" metadata panel (topics, website, features, duration, grades) + "Lesson Format" scale (1–5) + download button; right main content area
  - **History Content (Beyond the Textbook):** Two-column — left accordion sidebar (What Textbooks Say / What Historians Say / What Sources Say); right main content
  - **Best Practices:** Two-column — left "At a Glance" + "About the Author" panel with circular avatar; right main content
- Related Topics grid (2-column card grid) below main content

---

### Feature: Navigation Bar

**Description:**
Fixed top navigation bar present on all pages.

**Functionality:**
- Fixed position, ~60px height
- Logo (th_logo.png) on the left, linked to homepage
- Five nav links on the right, separated by pipe characters
- Active section highlighted in orange with bold text
- `aria-current` attribute for accessibility

---

### Feature: Footer

**Description:**
Site-wide footer with Quick Links bar and informational columns.

**Functionality:**
- **Quick Links bar** (black background): "Quick Links →" heading in yellow, followed by centered white pill buttons linking to: Teaching History Blog, National History Day Resources, Featured Activity
- **Footer body** (white background): 5-column grid with logo, site links, disclaimer, copyright, and Creative Commons license text
- **Bottom bar:** "Teachinghistory.Org Outreach | Privacy Policy" links

---

### Feature: Homepage

**Description:**
Landing page showcasing featured resources, grade-level browsing, and the site's mission.

**Functionality:**
- Hero/featured resources carousel with staggered content cards
- "Think Historically" banner with video CTA
- "Explore by Grade Level" — three cards (Elementary, Middle, High School)
- Footer

---

### Feature: Grade Level Pages

**Description:**
Browsing pages that aggregate resources by grade band (Elementary, Middle, High School).

**Functionality:**
- PageHero with grade level name on pale-blue background
- "Teacher's Pick" featured resource at top
- Resource category rows with colored label blocks (yellow for grade-band resources, green for classroom tools)
- Content cards in each row

---

### Feature: About Us / Staff Grid

**Description:**
Team page showing staff members with a bio modal.

**Functionality:**
- PageHero with "About Us" on pale-blue background
- "Staff" heading with "LEADERSHIP AND CONTENT TEAM" subheading
- 3-column grid of StaffCards (circular avatar, name, role, "Read Bio" button)
- Bio modal: white overlay card with avatar, name, role, and full bio text; `×` close button

---

## User Flows

### Flow 1: Browse a Content Section

**Goal:** Teacher discovers relevant resources within a content area.

**Steps:**
1. User clicks a section name in the navigation bar (e.g., "Teaching Materials")
2. Section index page loads with PageHero and carousel rows
3. User scans carousel rows to find a relevant subsection
4. User scrolls cards horizontally using arrow buttons to preview resources
5. User clicks a card → navigates to the detail page
6. Alternatively, user clicks "View All →" → navigates to the full subsection listing

---

### Flow 2: Explore by Grade Level

**Goal:** Teacher finds resources appropriate for their grade band.

**Steps:**
1. User visits homepage
2. User scrolls to "Explore by Grade Level" section
3. User clicks their grade level card (Elementary, Middle, or High School)
4. Grade level page loads with Teacher's Pick and category rows
5. User browses cards and clicks into a resource

---

### Flow 3: Read a Resource Detail Page

**Goal:** Teacher reads a full lesson plan review, article, or guide.

**Steps:**
1. User arrives at a detail page (from search engine, direct link, or site navigation)
2. User reads the sidebar metadata (At a Glance, Lesson Format, or accordion)
3. User reads the main content area
4. User browses Related Topics cards at the bottom for further reading

---

## Out of Scope

### Explicitly Excluded
- **Ask a Historian feature** — removed from this rebuild
- **Search functionality** — not visible in design spec, not planned for V1
- **User authentication / accounts** — site is fully public, no login
- **CMS admin interface** — content managed as Markdown files in the repository
- **Dynamic filtering or faceted search** on index pages
- **Comments or user-generated content**
- **Email newsletters or subscription management**

### Not in Design Spec
- **Digital Classroom section** — not included in Figma files; basic index page exists but no detailed design spec
- **Responsive / mobile design** — not explicitly specified in Figma; inferred breakpoints to be confirmed with design team

### Future Considerations
- Full-text search across all content
- Interactive quiz functionality (currently static content)
- RSS feeds for blog/new content

---

## Open Questions

### Design Questions
- **Q:** What are the exact responsive breakpoints and mobile layouts?
  - **Context:** Desktop designs exist but mobile/tablet layouts are inferred
  - **Status:** Pending design team input

- **Q:** Should the Digital Classroom section follow the same carousel layout as the other three sections?
  - **Context:** Digital Classroom is not in the Figma files but has content and a nav item
  - **Status:** Currently uses the generic section-index layout; may need its own design

### Content Questions
- **Q:** Are there content pages that don't belong to any of the four main sections?
  - **Context:** Legacy Drupal content includes misc directories (annual-report, press-release, enews, etc.)
  - **Status:** These exist in `content/` but don't have dedicated layouts yet

- **Q:** Should the blog section have its own layout or use the default list/single templates?
  - **Context:** Blog content exists but isn't referenced in the design spec
  - **Status:** Open

---

*Last Updated: 2026-03-10*
*This document is maintained for AI agent context and onboarding.*
