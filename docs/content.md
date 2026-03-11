# Managing Content

All site content lives in `teachinghistory-website/content/`. Hugo uses the directory structure to determine sections and URLs.

## Content sections

| Section               | URL prefix              | Color   | Subsections                                                        |
|-----------------------|-------------------------|---------|--------------------------------------------------------------------|
| Teaching Materials    | `/teaching-materials/`  | orange  | ask-a-master-teacher, teaching-guides, lesson-plan-reviews, english-language-learners |
| History Content       | `/history-content/`     | yellow  | ask-a-historian, beyond-the-textbook, website-reviews, national-resources, quiz |
| Best Practices        | `/best-practices/`      | green   | teaching-with-textbooks, examples-of-teaching, examples-of-historical-thinking |
| Digital Classroom     | `/digital-classroom/`   | pale-blue | tech-for-teachers, beyond-the-chalkboard, ask-a-digital-historian |

## Creating new content

Use the `just new` command, which wraps `hugo new`:

```bash
# Create a new teaching guide
just new teaching-materials/teaching-guides/my-new-guide.md

# Create a new history content article
just new history-content/ask-a-historian/my-article.md

# Create a new best practices post
just new best-practices/teaching-with-textbooks/my-post.md
```

This uses the section archetype (e.g., `archetypes/teaching-materials.md`) to scaffold the frontmatter. The new file will be created as a draft.

## Frontmatter reference

### Common fields (all sections)

| Field          | Description                                  | Required |
|----------------|----------------------------------------------|----------|
| `title`        | Page title                                   | Yes      |
| `date`         | Publication date (ISO 8601)                  | Yes      |
| `draft`        | Set to `true` to hide from production builds | Yes      |
| `summary`      | Short description (shown in sidebar cards)   | No       |
| `splash_image` | Path to hero image, relative to `/static/`   | No       |
| `author_bio`   | Author biography text                        | No       |
| `author_image` | Path to author photo                         | No       |

### History Content (Beyond the Textbook)

These fields populate the collapsible sidebar cards:

| Field                | Description                              |
|----------------------|------------------------------------------|
| `question`           | Guiding question (shown as italic subheading) |
| `what_textbooks_say` | Content for "What Textbooks Say" card    |
| `what_historians_say`| Content for "What Historians Say" card   |
| `what_sources_say`   | Content for "What Sources Say" card      |

### Teaching Materials (Lesson Plan Reviews)

| Field              | Description                              |
|--------------------|------------------------------------------|
| `website_url`      | URL of the lesson plan being reviewed    |
| `flexibility_scale`| Rating for lesson flexibility (1-5)      |

### Digital Classroom

| Field         | Description                     |
|---------------|---------------------------------|
| `question`    | Guiding question                |
| `website_url` | URL of the tool or resource     |

### Legacy fields

These fields are from the Drupal migration and are not used in templates:

| Field              | Description                              |
|--------------------|------------------------------------------|
| `content_type`     | Original Drupal content type             |
| `drupal_nid`       | Original Drupal node ID                  |
| `splash_image_fid` | Drupal file ID (resolved to `splash_image`) |
| `thumbnail_fid`    | Drupal file ID (resolved to `thumbnail`) |
| `author_image_fid` | Drupal file ID (resolved to `author_image`) |

## Publishing workflow

1. Create content with `just new` (creates as draft)
2. Edit the file, fill in frontmatter and body content
3. Preview locally with `just serve`
4. When ready, set `draft: false` in frontmatter
5. Build for production with `just build`

Note: `just serve` does **not** show draft content. Use `just build-drafts` to preview drafts.

## Images

Place images in `teachinghistory-website/static/files/` and reference them as `/files/my-image.jpg` in frontmatter or body content. Most existing images were migrated from the Drupal site and live in this directory.
