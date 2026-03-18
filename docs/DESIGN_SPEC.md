# Teaching History Design Spec 

Teachinghistory.org is a K–12 history education resource site created by the Roy Rosenzweig Center for History and New Media (CHNM) at George Mason University, with funding from the U.S. Department of Education. The site provides lesson plans, teaching guides, primary source reviews, best practices, and historian Q&A resources for elementary, middle, and high school teachers.

NOTE: For some of the pages to work we may want to think about restructuring our `content/` for Hugo.

## Tech Stack

- Framework: Hugo 
- Styling: Tailwind

# Design Tokens 

## Colors

```css
--color-orange:        #F26522;
--color-orange-tint:   #FFFAF8;
--color-yellow:        #FFC20E;
--color-yellow-tint:   #FBF9F4;
--color-green:         #37A99C;
--color-green-tint:    #F5FBFA;
--color-black:         #000000;
--color-pale-blue:     #DCEBF9;
--color-pale-blue-tint: #F5FAFF;
--color-dark:          #1a1a1a;   /* footer background — near-black */
--color-white:         #FFFFFF;
--color-gray-light:    #E5E5E5;   /* card image placeholder bg */
```

## Section Color Mapping

Each top-level section uses a distinct accent color for its header banner and UI elements:

| Section             | Accent Color      | Tint               |
|---------------------|-------------------|--------------------|
| Teaching Materials  | `--color-orange`  | `--color-orange-tint` |
| History Content     | `--color-yellow`  | `--color-yellow-tint` |
| Best Practices      | `--color-green`   | `--color-green-tint`  |
| About Us            | `--color-pale-blue` | `--color-pale-blue-tint` |
| Grade Level pages   | `--color-pale-blue` | `--color-pale-blue-tint` |

## Navigation header

left: th_logo.png
right: "About Us", "Teaching Materials", "Best Practices", "Digital Classroom"

## Design Components

Each of the Navigation sections have their own color scheme. 
- Teaching Materials: orange and orange tint. 
- History Content: yellow and yellow tint 
- Best Practices: green and green tint 
- About Us AND other pages that don't fall into one of the three above areas: pale blue and pale blue tint

## Typography

```css
--font-heading: 'Lora', serif;
--font-body:    'Roboto Slab', serif;

/* Scale (approximate from designs) */
--text-xs:   0.75rem;
--text-sm:   0.875rem;
--text-base: 1rem;
--text-lg:   1.125rem;
--text-xl:   1.25rem;
--text-2xl:  1.5rem;
--text-3xl:  1.875rem;
--text-4xl:  2.25rem;
```

## Global Components

### NavBar

- **Layout:** Fixed top. Logo left (th_logo.png), nav links right.
- **Logo:** `teachinghistory.org` 
- **Nav links:** About Us | Teaching Materials | History Content | Best Practices | Digital Classroom
- **Separator:** Thin vertical pipes `|` between nav items
- **Active state:** Active section link renders in the section accent color (e.g., orange for Teaching Materials)
- **Height:** ~60px

### PageHero

Reused across all section index and detail pages.

- **Layout:** Full-width banner, fixed height (~100px), section accent color background
- **Content:** Single centered `<h1>` in a black rectangular pill/badge with white text
- **Font:** Lora, ~28–32px

### ContentCard

Used in all horizontal carousels and grid listings.

- **Structure:**
  - Title (top, above image, Lora ~14px, bold)
  - Image (fixed-height rectangle, ~160px tall; gray `#E5E5E5` placeholder when no image)
  - Body text (Roboto Slab, ~13px, 3–4 lines max, truncate with ellipsis)
- **Border:** 1px solid light gray
- **No explicit CTA button** — entire card is likely clickable
- **Width:** ~250px fixed; cards overflow horizontally in carousel

### HorizontalCarousel

Used on all section index pages. Each content category gets one carousel row.

- **Layout:** Left column (~200px) contains category label + description + "View All" button. Right side is a scrollable row of `ContentCard` components.
- **Navigation:** Left `←` and right `→` arrow buttons below the card row
- **Overflow:** Cards clip at the right edge, implying more content beyond viewport
- **"View All" button:** Orange/Yellow/Green pill button (matches section accent) with `→` arrow

### Footer

- Above the footer: a single black bar. On the left are a header font Quick Links with a right arrow pointing at three white buttons: "Teaching History Blog," "National History Day Resources," and "Featured Activity."
- Below the black bar, a white footer in five columns. 
- **Layout:** 5-column grid
  - Col 1: teachinghistory.org logo (th_logo_stacked.png)
  - Col 2: Site links — Staff, Project Partners, Technical Working Group, Research Advisors. Each link is stacked, and separated by a light gray border-bottom.
  - Col 3: Disclaimer text: "The content of this website does not necessarily reflect the views or policies of the U.S. Department of Education nor does mention of trade names, commercial products, or organizations imply endorsement by the U.S. Government."
  - Col 4: Copyright: "© 2026 Created by the Roy Rosenzweig Center for History and New Media at George Mason University with funding from the U.S. Department of Education (Contract Number ED-07-CO-0088)"
  - Col 5: CC text: "Except where otherwise noted, the content on this site is licensed under a Creative Commons Attribution Non-Commercial Share Alike 3.0 License."
- **Bottom bar:** Single centered line. Below that: "Teachinghistory.Org Outreach | Privacy Policy"
- **Font size:** ~12px, light gray on black

## Pages & Routes

| Page                          | Route (assumed)                        |
|-------------------------------|----------------------------------------|
| Homepage                      | `/`                                    |
| Teaching Materials index      | `/teaching-materials/`                 |
| Teaching Materials detail     | `/teaching-materials/:slug/`           |
| History Content index         | `/history-content/`                    |
| History Content detail        | `/history-content/:slug/`              |
| Best Practices index          | `/best-practices/`                     |
| Best Practices detail         | `/best-practices/:slug/`               |
| Elementary School Teachers    | `/grade-level/elementary/`             |
| Middle School Teachers        | `/grade-level/middle/`                 |
| High School Teachers          | `/grade-level/high/`                   |
| About Us / Staff              | `/about/`                              |
| Digital Classroom             | `/digital-classroom/` *(not in spec)*  |


### ArrowButton (inline CTA)

- **Style:** Rounded pill, solid fill in section accent color, white text, right-arrow icon
- **Variants:** "View All →", "Read More →", "Download Lesson Plan →"
- **Also used:** As a plain text link with just an `→` (e.g., "Explore Our Resources and Materials →" on homepage)

## Page Specifications

### 1. Homepage

**Route:** `/`

**Sections (top to bottom):**

#### 1a. Hero / Featured Resources Carousel

- **Background:** Light gray or white
- **Left side (~25% width):** Large display text — "Explore Our Resources and Materials" — Lora, ~36px. Below: plain `→` text arrow link.
- **Right side (~75% width):** Three overlapping/offset content feature cards for Teaching Materials, History Content, and Best Practices. Each card has:
  - Category label (e.g., "Teaching Materials") top-left in white on dark overlay
  - Featured image (fills card)
  - Pull-quote or description text in a colored overlay box (orange for TM, yellow/teal for HC)
  - `→` arrow button bottom-right
- **Layout note:** Cards are staggered vertically — Teaching Materials card slightly lower, History Content in middle, Best Practices slightly higher. Partial visibility suggests this may be a carousel.

#### 1b. Think Historically Banner

- **Layout:** Full-width, ~50% image / ~50% text split
- **Left:** Collage of historical B&W photographs (civil rights, WWII, Woodstock, MLK, etc.)
- **Right:** White background
  - Heading: "Think Historically" — Lora, large, in section orange
  - Body paragraph: site description text
  - CTA: "▶ View Video" — outlined pill button

#### 1c. Explore by Grade Level

- **Heading:** "Explore by Grade Level" — centered, Lora
- **Layout:** Three equal-width cards in a row
  - Each: full-width photo of classroom setting + label below ("Elementary School Teachers", "Middle School Teachers", "High School Teachers") + `→` arrow
  - Bottom of each card: label bar with text + arrow on white/light background

#### 1d. AskAHistorianBanner *(see global)*

#### 1e. Footer *(see global)*

### 2. Teaching Materials Index

**Route:** `/teaching-materials/`

**Header:** PageHero — orange background, "Teaching Materials"

**Nav active:** "Teaching Materials" in orange

**Content:** Four HorizontalCarousel rows:
1. **Lesson Plan Reviews** — "Evaluate key elements of effective teaching"
2. **Teaching Guides** — "Explore new teaching methods and approaches"
3. **English Language Learners** — "Instructional strategies and resources for ELL"
4. *(Additional categories may exist — three visible in spec)*

### 3. Teaching Materials Detail

**Route:** `/teaching-materials/:slug/`

**Example:** "Abraham Lincoln and the Jews"

**Header:** PageHero — orange background, "Teaching Materials"

**Breadcrumb:** `LESSON PLAN REVIEWS` (uppercase label) + `← View all Teaching Materials` link

**Layout:** Two-column (sidebar left ~30%, main content right ~70%)

#### Left Sidebar

Two distinct panels:

**Panel 1 — At a Glance**
- Header: "At a Glance" — Lora, large
- Fields (each separated by horizontal rule):
  - **TOPICS** (uppercase label) + topic text
  - **WEBSITE** (uppercase label) + linked external site name
  - **FEATURES** (uppercase label) + comma-separated list of pedagogical features
  - **DURATION** (uppercase label) + time (e.g., "90 minutes")
  - **GRADE(S)** (uppercase label) + grade number(s)

**Panel 2 — Lesson Format**
- Header: "Lesson Format" — Lora, large
- Interactive 1–5 scale with filled circles; selected circle is filled black, others are outlined
- Below scale: "Unstructured ←——→ Structured" label
- CTA: Orange pill button — "Download Lesson Plan →"

#### Main Content

- **Title:** Lora, ~32px
- **Hero image:** Full-width, max ~460px tall
- **Lede/summary paragraph:** Roboto Slab
- **Body sections with bold headings:** "Review", etc. — bold inline headings (h3 style)
- **Linked text:** Standard underlined links within body copy

#### Related Topics (below main content, full-width)

- **Heading:** "Related Topics" — Lora
- **Layout:** 2-column card grid
- Each card: Title top, image middle, body text below
- Uses ContentCard component

### 4. History Content Index

**Route:** `/history-content/`

**Header:** PageHero — yellow (`#FFC20E`) background, "History Content"

**Nav active:** "History Content" in yellow/orange

**Content:** Four HorizontalCarousel rows (yellow accent "View All" buttons):
1. **Website Reviews** — "Find quality websites & primary sources"
2. **Beyond the Textbook** — "Question textbook narratives"
3. **History Quiz** — "Test your history knowledge"
4. **National Resources** — "Test your history knowledge" *(description likely placeholder)*

### 5. History Content Detail — Beyond the Textbook

**Route:** `/history-content/:slug/`

**Example:** "How significant is the Tet Offensive..."

**Header:** PageHero — yellow background, "History Content"

**Breadcrumb:** `BEYOND THE TEXTBOOK` + `← View all History Content`

**Layout:** Two-column (sidebar left ~30%, main content right ~70%)

#### Left Sidebar — Accordion

Three collapsible sections:
- **WHAT TEXTBOOKS SAY** — expanded by default; shows summary text
- **WHAT HISTORIANS SAY** — collapsed (chevron right)
- **WHAT SOURCES SAY** — collapsed (chevron right)

Expanded state: chevron points down, section label + body text visible in a bordered panel.

#### Main Content

- **Title:** Large Lora — phrased as "Central Question: [question text]"
- **Hero image:** Full-width
- **Body paragraphs:** Roboto Slab

#### Related Topics — same as Teaching Materials detail

### 6. Best Practices Index

**Route:** `/best-practices/`

**Header:** PageHero — green (`#37A99C`) background, "Best Practices"

**Nav active:** "Best Practices" in green

**Content:** Four HorizontalCarousel rows (green accent "View All" buttons):
1. **Historical Thinking** — "Scholars, students, and teachers model historical thinking"
2. **Teaching in Action** — "Teachers demonstrate promising teaching practices"
3. **Teaching with Textbooks** — "Techniques for promoting historical inquiry"
4. **Using Primary Sources** — "Strategies for analyzing primary sources"

### 7. Best Practices Detail

**Route:** `/best-practices/:slug/`

**Example:** "Using Historiography to Analyze the Mexican-American War"

**Header:** PageHero — green background, "Best Practices"

**Breadcrumb:** `TEACHING WITH TEXTBOOKS` + `← View all Best Practices`

**Layout:** Two-column (sidebar ~30%, main ~70%)

#### Left Sidebar — Two Panels

**Panel 1 — At a Glance**
- **DESCRIPTION** (uppercase label) + description text
*(Simpler than Teaching Materials; no grade/duration fields visible in this example)*

**Panel 2 — About the Author**
- Header: "About the Author" — Lora
- Circular avatar image (gray placeholder ~120px diameter)
- Author name + bio text below

#### Main Content

- Title, hero image, body text with headings ("What is it?", "Example") and numbered list for activity steps
- Excerpt blocks with bold "EXCERPT #1: [YEAR]" label + bold h3-style sub-heading summarizing the excerpt + citation line + body text

### 8. About Us — Staff Grid

**Route:** `/about/`

**Header:** PageHero — pale blue (`#DCEBF9`) background, "About Us"

**Nav active:** "About Us"

**Layout:**

- **Section heading:** "Staff" — Lora, centered, large
- **Sub-heading:** "LEADERSHIP AND CONTENT TEAM" — uppercase, small, centered
- **Grid:** 3-column responsive grid of StaffCard components

#### StaffCard

- Circular avatar image (~160px diameter, gray placeholder)
- Name — Lora, ~20px
- Title/Role — uppercase, small, letter-spaced
- "Read Bio" button — solid black pill button, white text

### 9. Staff Bio Modal

Triggered by "Read Bio" button on About Us page.

- **Overlay:** Semi-transparent dark background covering full page
- **Modal:** White card, centered, ~480px wide, scrollable
  - `×` close button top-right
  - Circular avatar (~120px)
  - Name — Lora, large
  - Role — uppercase, small
  - Bio text — Roboto Slab, with hyperlinks inline

### 10–12. Grade Level Pages

**Routes:** `/grade-level/elementary/`, `/grade-level/middle/`, `/grade-level/high/`

**Header:** PageHero — pale blue background, grade level name ("Elementary School Teachers", "Middle School Teachers", "High School Teachers")

**Layout (top to bottom):**

#### Teacher's Pick Feature

- **Label:** "TEACHER'S PICK" — uppercase, small, in section accent color (orange for elementary, presumably consistent across grade levels)
- **Layout:** Two-column — left: title + description + "Read More →" button; right: large featured image (~460px wide)
- **Title font:** Lora, large (~32–36px)
- **Button:** Black solid pill, "Read More →"

#### Resource Category Rows

Two rows visible per page:

**Row 1 — Grade Band Resources**
- Left: Colored block label (yellow `#FFC20E` background) — e.g., "K-12 Resources", "6-8 Resources", "9-12 Resources" — Lora, large, white text
- Right: 2+ ContentCards (same card pattern as section index pages)
- *Note: Elementary page shows K-12 and 3-5 rows; this suggests multiple grade-band sections per page*

**Row 2 — Classroom Tools**
- Left: Teal (`#37A99C`) block label — "Classroom Tools" — Lora, large, white text
- Right: 2+ ContentCards

**Grade band label colors:**
- K-12 / grade band resources: Yellow (`#FFC20E`)
- Classroom Tools: Teal/Green (`#37A99C`)

## Component Inventory Summary

| Component              | Used On                                      |
|------------------------|----------------------------------------------|
| NavBar                 | All pages                                    |
| PageHero               | All section + detail pages                   |
| ContentCard            | All index pages, detail Related Topics       |
| HorizontalCarousel     | All section index pages                      |
| AskAHistorianBanner    | All pages (pre-footer)                       |
| Footer                 | All pages                                    |
| ArrowButton            | Index pages, homepage, detail pages          |
| AtAGlanceSidebar       | Teaching Materials detail, Best Practices detail |
| LessonFormatScale      | Teaching Materials detail only               |
| AccordionSidebar       | History Content detail (Beyond the Textbook) |
| AboutTheAuthorSidebar  | Best Practices detail                        |
| StaffCard              | About Us                                     |
| BioModal               | About Us (triggered by StaffCard)            |
| TeachersPick           | Grade Level pages                            |
| CategoryLabelBlock     | Grade Level pages (colored square label)     |
| RelatedTopicsGrid      | Detail pages (2-col card grid)               |

## Responsive Behavior

*Not explicitly specified in Figma files — the following is inferred:*

- **Desktop:** All layouts as described above (~1280px design width)
- **Tablet:** HorizontalCarousels likely reduce visible card count; sidebar may stack above main content on detail pages
- **Mobile:** Single-column throughout; NavBar collapses to hamburger; carousels remain horizontally scrollable

*Confirm breakpoints with design team before implementing.*

## Out of Scope

- Digital Classroom section (not included in Figma files)
- Search functionality (not visible in any frame)
- User authentication / accounts
- Any CMS admin interface
- Dynamic filtering or faceted search on index pages