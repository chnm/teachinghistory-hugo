# Hugo project commands for teachinghistory.org

# Default recipe - list available commands
default:
    @just --list

# Hugo site directory
site := "teachinghistory-website"

# Start development server with live reload
serve:
    cd {{site}} && hugo server --navigateToChanged

# Install npm dependencies (Tailwind/PostCSS devDependencies, pagefind's native binary)
install:
    cd {{site}} && npm install

# Build the site for production (Hugo + Pagefind index)
build: install
    cd {{site}} && npm run build

# Build the site including drafts
build-drafts:
    cd {{site}} && hugo -D

# Rebuild Tailwind CSS (clears Hugo's cached assets and rebuilds)
css:
    rm -rf {{site}}/resources/_gen
    cd {{site}} && hugo --minify

# Generate the Pagefind index from an existing production build
search: install
    cd {{site}} && npm run build:search

# Clean generated files
clean:
    rm -rf {{site}}/public {{site}}/resources/_gen

# Create a new content file (usage: just new posts/my-post.md)
new path:
    cd {{site}} && hugo new content/{{path}}

# Check for broken internal links and other issues
check:
    cd {{site}} && hugo --printUnusedTemplates --printPathWarnings

# --- Legacy-URL redirect pipeline (Drupal -> Hugo -> Caddy) ---

# One-time, idempotent: move legacy `url:` frontmatter into `aliases:` (dry run without --apply)
redirects-relocate *args:
    uv run utils/relocate_urls.py {{args}}

# Build the legacy->native map: Hugo manifest + node_redirects.tsv (Drupal path_alias dump)
redirects-build:
    uv run utils/redirect_mapper.py build

# Generate utils/taxonomy_redirects.csv from taxonomy_aliases.tsv + the Hugo manifest
redirects-taxonomy:
    uv run utils/redirect_mapper.py taxonomy

# Merge old_urls.csv + taxonomy_redirects.csv + apply the parent-section fallback
redirects-reconcile:
    uv run utils/redirect_mapper.py reconcile

# Generate teachinghistory-website/static/redirects.caddy (Hugo then copies it to public/redirects.caddy)
redirects-generate:
    uv run utils/redirect_mapper.py generate

# Regenerate the whole map+snippet (requires a prior `just build`)
redirects: redirects-build redirects-taxonomy redirects-reconcile redirects-generate

# Regenerate against the deployed Hugo manifest instead of a local build (no Hugo needed)
redirects-remote manifest="https://dev.teachinghistory.org/redirects.json":
    uv run utils/redirect_mapper.py build --manifest {{manifest}}
    uv run utils/redirect_mapper.py taxonomy --manifest {{manifest}}
    uv run utils/redirect_mapper.py reconcile --manifest {{manifest}}
    uv run utils/redirect_mapper.py generate

# Cross-check the live old Drupal site: /node/{nid} should 301 to our recorded alias
redirects-crosscheck old_site="https://teachinghistory.org" *args:
    uv run utils/redirect_mapper.py crosscheck --old-site {{old_site}} {{args}}

# Verify redirects against a running target (301 -> native 200, no loops)
redirects-verify target="http://localhost:8080" *args:
    uv run utils/redirect_mapper.py verify --target {{target}} {{args}}

# Reconcile a local normalized remediation tracker against current Hugo content
content-audit tracker="reports/content_remediation_tracker.csv":
    python3 utils/content_remediation_audit.py --tracker "{{tracker}}"

# Inventory the Drupal field tables consumed by the extractor
drupal-field-inventory sql_dump="utils/th_db.sql":
    python3 utils/drupal_field_inventory.py --sql-dump "{{sql_dump}}"

# Docker build
docker-build tag="teachinghistory:latest":
    docker build -t {{tag}} {{site}}

# Docker run (serves on port 8080)
docker-run tag="teachinghistory:latest":
    docker run -p 8080:80 {{tag}}

# Build and run Docker container
docker-up: docker-build docker-run
