# Hugo project commands for teachinghistory.org

# Default recipe - list available commands
default:
    @just --list

# Hugo site directory
site := "teachinghistory-website"

# Start development server with live reload
serve:
    cd {{site}} && hugo server -D --navigateToChanged

# Start dev server binding to all interfaces (for testing on other devices)
serve-lan:
    cd {{site}} && hugo server -D --bind 0.0.0.0 --baseURL http://localhost:1313

# Build the site for production
build:
    cd {{site}} && hugo --minify

# Build the site including drafts
build-drafts:
    cd {{site}} && hugo -D

# Clean generated files
clean:
    rm -rf {{site}}/public {{site}}/resources/_gen

# Create a new content file (usage: just new posts/my-post.md)
new path:
    cd {{site}} && hugo new content/{{path}}

# Show site stats
stats:
    cd {{site}} && hugo --printMemoryUsage --printPathWarnings

# Check for broken internal links and other issues
check:
    cd {{site}} && hugo --printUnusedTemplates --printPathWarnings

# Docker build
docker-build tag="teachinghistory:latest":
    docker build -t {{tag}} {{site}}

# Docker run (serves on port 8080)
docker-run tag="teachinghistory:latest":
    docker run -p 8080:80 {{tag}}

# Build and run Docker container
docker-up: docker-build docker-run

# Watch for changes and rebuild (without server)
watch:
    cd {{site}} && hugo --watch
