# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests",
#     "beautifulsoup4",
#     "pyyaml",
# ]
# ///
"""
External link inventory and checker for teachinghistory.org Hugo site.

Usage:
    uv run utils/link_checker.py extract              # Build link inventory CSV
    uv run utils/link_checker.py check                # Check links from inventory
    uv run utils/link_checker.py check --resume       # Resume interrupted check run
    uv run utils/link_checker.py check --limit 100    # Check only first N unchecked links
    uv run utils/link_checker.py wayback              # Look up Wayback Machine snapshots for dead links
    uv run utils/link_checker.py wayback --resume     # Resume interrupted wayback run
"""

import argparse
import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml
from bs4 import BeautifulSoup

CONTENT_DIR = Path(__file__).resolve().parent.parent / "teachinghistory-website" / "content"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "utils"
INVENTORY_CSV = OUTPUT_DIR / "link_inventory.csv"
RESULTS_CSV = OUTPUT_DIR / "link_results.csv"

# Domains to exclude (internal links)
INTERNAL_DOMAINS = {
    "teachinghistory.org",
    "www.teachinghistory.org",
    "dev.teachinghistory.org",
    "localhost",
}

# Patterns in page titles that suggest a hijacked/parked domain
SUSPICIOUS_TITLE_WORDS = [
    "casino", "poker", "gambling", "slot", "betting",
    "buy this domain", "domain for sale", "parked", "is for sale",
    "adult", "xxx", "porn",
    "404", "not found", "page not found",
    "403", "forbidden", "access denied",
    "error", "default web page",
    "website expired", "account suspended", "account has been suspended",
    "coming soon", "under construction",
]

REQUEST_TIMEOUT = 15
REQUEST_DELAY = 0.3  # seconds between requests
USER_AGENT = "TeachingHistory-LinkChecker/1.0 (educational site maintenance)"


# --- Extract phase ---

def parse_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter from a markdown file."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return {}
    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}


def extract_links(text: str) -> list[tuple[str, str]]:
    """Extract (link_text, url) pairs from markdown + HTML content."""
    links = []
    # Markdown links: [text](url)
    for m in re.finditer(r"\[([^\]]*)\]\(([^)]+)\)", text):
        links.append((m.group(1).strip(), m.group(2).strip()))
    # HTML href links: <a href="url">text</a>
    for m in re.finditer(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', text, re.IGNORECASE | re.DOTALL):
        link_text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        links.append((link_text, m.group(1).strip()))
    return links


def is_external(url: str) -> bool:
    """Check if a URL is external (not teachinghistory.org or relative)."""
    if not url or url.startswith("#") or url.startswith("mailto:") or url.startswith("tel:"):
        return False
    parsed = urlparse(url)
    if not parsed.scheme and not parsed.netloc:
        return False  # relative link
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return False
    host = parsed.netloc.lower()
    return host not in INTERNAL_DOMAINS


def get_section(rel_path: Path) -> str:
    """Get the top-level section from a content file's relative path."""
    parts = rel_path.parts
    return parts[0] if parts else ""


def run_extract():
    """Scan all content files and build an external link inventory CSV."""
    print(f"Scanning {CONTENT_DIR} for external links...")
    rows = []
    file_count = 0
    for md_file in sorted(CONTENT_DIR.rglob("*.md")):
        file_count += 1
        text = md_file.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter(text)
        page_title = fm.get("title", "")
        page_url = fm.get("url", "")
        rel_path = md_file.relative_to(CONTENT_DIR)
        section = get_section(rel_path)

        for link_text, url in extract_links(text):
            if is_external(url):
                rows.append({
                    "section": section,
                    "page_title": page_title,
                    "page_url": page_url,
                    "source_file": str(rel_path),
                    "link_url": url,
                    "link_text": link_text,
                })

    # Dedupe exact (source_file, link_url) pairs
    seen = set()
    deduped = []
    for row in rows:
        key = (row["source_file"], row["link_url"])
        if key not in seen:
            seen.add(key)
            deduped.append(row)

    fieldnames = ["section", "page_title", "page_url", "source_file", "link_url", "link_text"]
    with open(INVENTORY_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(deduped)

    unique_urls = len({r["link_url"] for r in deduped})
    print(f"Scanned {file_count} files.")
    print(f"Found {len(deduped)} external link references ({unique_urls} unique URLs).")
    print(f"Inventory written to {INVENTORY_CSV}")


# --- Check phase ---

def check_url(url: str, session: requests.Session) -> dict:
    """Check a single URL. Returns status info dict."""
    result = {
        "http_status": "",
        "final_url": "",
        "remote_title": "",
        "redirect_domain_changed": False,
        "needs_review": False,
        "reason": "",
    }
    try:
        resp = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        result["http_status"] = resp.status_code
        result["final_url"] = resp.url

        # Check if redirect changed domain
        orig_domain = urlparse(url).netloc.lower().lstrip("www.")
        final_domain = urlparse(resp.url).netloc.lower().lstrip("www.")
        if orig_domain != final_domain:
            result["redirect_domain_changed"] = True

        # Extract title for 200 responses
        if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
            soup = BeautifulSoup(resp.text[:50000], "html.parser")
            title_tag = soup.find("title")
            if title_tag:
                result["remote_title"] = title_tag.get_text(strip=True)[:200]

        # Determine if needs review
        reasons = []
        if resp.status_code >= 400:
            reasons.append(f"HTTP {resp.status_code}")
        if result["redirect_domain_changed"]:
            reasons.append(f"redirected to different domain: {final_domain}")
        title_lower = result["remote_title"].lower()
        for word in SUSPICIOUS_TITLE_WORDS:
            if word in title_lower:
                reasons.append(f"suspicious title keyword: '{word}'")
                break

        if reasons:
            result["needs_review"] = True
            result["reason"] = "; ".join(reasons)

    except requests.exceptions.SSLError:
        result["http_status"] = "SSL_ERROR"
        result["needs_review"] = True
        result["reason"] = "SSL certificate error"
    except requests.exceptions.ConnectionError:
        result["http_status"] = "CONN_ERROR"
        result["needs_review"] = True
        result["reason"] = "Connection failed (site may be down)"
    except requests.exceptions.Timeout:
        result["http_status"] = "TIMEOUT"
        result["needs_review"] = True
        result["reason"] = f"Timed out after {REQUEST_TIMEOUT}s"
    except requests.exceptions.TooManyRedirects:
        result["http_status"] = "TOO_MANY_REDIRECTS"
        result["needs_review"] = True
        result["reason"] = "Too many redirects"
    except requests.exceptions.RequestException as e:
        result["http_status"] = "ERROR"
        result["needs_review"] = True
        result["reason"] = str(e)[:200]

    return result


def run_check(resume: bool = False, limit: int | None = None):
    """Read inventory CSV, check each unique URL, write results CSV."""
    if not INVENTORY_CSV.exists():
        print(f"No inventory found at {INVENTORY_CSV}. Run 'extract' first.")
        sys.exit(1)

    # Read inventory
    with open(INVENTORY_CSV, encoding="utf-8") as f:
        inventory = list(csv.DictReader(f))
    print(f"Loaded {len(inventory)} link references from inventory.")

    # Get unique URLs
    unique_urls = sorted({row["link_url"] for row in inventory})
    print(f"Found {len(unique_urls)} unique URLs to check.")

    # Load already-checked URLs if resuming (only rows with actual results)
    checked = {}
    if resume and RESULTS_CSV.exists():
        with open(RESULTS_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("http_status", ""):
                    checked[row["link_url"]] = row
        print(f"Resuming: {len(checked)} URLs already checked.")

    # Check URLs
    url_results = {}
    urls_to_check = [u for u in unique_urls if u not in checked]
    if limit:
        urls_to_check = urls_to_check[:limit]
    total = len(urls_to_check)
    print(f"Checking {total} URLs...")

    session = requests.Session()
    for i, url in enumerate(urls_to_check, 1):
        if i % 50 == 0 or i == 1:
            print(f"  [{i}/{total}] checking {url[:80]}...")
        result = check_url(url, session)
        url_results[url] = result
        time.sleep(REQUEST_DELAY)

    # Merge with previously checked
    for url, row in checked.items():
        url_results[url] = {
            "http_status": row.get("http_status", ""),
            "final_url": row.get("final_url", ""),
            "remote_title": row.get("remote_title", ""),
            "redirect_domain_changed": row.get("redirect_domain_changed", ""),
            "needs_review": row.get("needs_review", ""),
            "reason": row.get("reason", ""),
        }

    # Build output: one row per (source_file, link_url) with check results merged
    fieldnames = [
        "section", "page_title", "page_url", "source_file",
        "link_url", "link_text",
        "http_status", "final_url", "remote_title",
        "redirect_domain_changed", "needs_review", "reason",
    ]
    output_rows = []
    for row in inventory:
        url = row["link_url"]
        result = url_results.get(url, {})
        output_rows.append({
            **row,
            "http_status": result.get("http_status", ""),
            "final_url": result.get("final_url", ""),
            "remote_title": result.get("remote_title", ""),
            "redirect_domain_changed": result.get("redirect_domain_changed", ""),
            "needs_review": result.get("needs_review", ""),
            "reason": result.get("reason", ""),
        })

    with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    flagged = sum(1 for r in output_rows if str(r["needs_review"]) == "True")
    print(f"\nResults written to {RESULTS_CSV}")
    print(f"Total link references: {len(output_rows)}")
    print(f"Flagged for review: {flagged}")


# --- Wayback phase ---

WAYBACK_CSV = OUTPUT_DIR / "link_wayback.csv"
WAYBACK_API = "https://archive.org/wayback/available"
WAYBACK_DELAY = 0.5  # be polite to archive.org

# Statuses that indicate a dead/broken link worth looking up in Wayback
DEAD_STATUSES = {
    "404", "410", "CONN_ERROR", "TIMEOUT", "SSL_ERROR",
    "ERROR", "TOO_MANY_REDIRECTS", "500", "502", "503", "504",
    "520", "521", "530", "526",
}


def lookup_wayback(url: str, session: requests.Session) -> dict:
    """Query the Wayback Machine Availability API for a snapshot."""
    result = {"wayback_url": "", "wayback_timestamp": "", "wayback_status": ""}
    try:
        resp = session.get(
            WAYBACK_API,
            params={"url": url},
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code == 200:
            data = resp.json()
            snapshot = data.get("archived_snapshots", {}).get("closest", {})
            if snapshot and snapshot.get("available"):
                result["wayback_url"] = snapshot.get("url", "")
                result["wayback_timestamp"] = snapshot.get("timestamp", "")
                result["wayback_status"] = "found"
            else:
                result["wayback_status"] = "not_archived"
        else:
            result["wayback_status"] = f"api_error_{resp.status_code}"
    except requests.exceptions.RequestException as e:
        result["wayback_status"] = f"error: {str(e)[:100]}"
    return result


def run_wayback(resume: bool = False, limit: int | None = None):
    """Look up Wayback Machine snapshots for dead links."""
    if not RESULTS_CSV.exists():
        print(f"No results found at {RESULTS_CSV}. Run 'check' first.")
        sys.exit(1)

    # Read full results
    with open(RESULTS_CSV, encoding="utf-8") as f:
        results = list(csv.DictReader(f))

    # Get unique dead URLs
    dead_urls = sorted({
        r["link_url"] for r in results
        if r.get("http_status", "") in DEAD_STATUSES
    })
    print(f"Found {len(dead_urls)} unique dead URLs to look up in Wayback Machine.")

    # Load already-looked-up URLs if resuming
    checked = {}
    if resume and WAYBACK_CSV.exists():
        with open(WAYBACK_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("wayback_status", ""):
                    checked[row["link_url"]] = row
        print(f"Resuming: {len(checked)} URLs already looked up.")

    urls_to_check = [u for u in dead_urls if u not in checked]
    if limit:
        urls_to_check = urls_to_check[:limit]
    total = len(urls_to_check)
    print(f"Looking up {total} URLs...")

    wayback_results = {}
    session = requests.Session()
    for i, url in enumerate(urls_to_check, 1):
        if i % 50 == 0 or i == 1:
            print(f"  [{i}/{total}] looking up {url[:80]}...")
        wayback_results[url] = lookup_wayback(url, session)
        time.sleep(WAYBACK_DELAY)

    # Merge with previously checked
    for url, row in checked.items():
        wayback_results[url] = {
            "wayback_url": row.get("wayback_url", ""),
            "wayback_timestamp": row.get("wayback_timestamp", ""),
            "wayback_status": row.get("wayback_status", ""),
        }

    # Build output: only dead links, enriched with wayback data
    fieldnames = [
        "section", "page_title", "page_url", "source_file",
        "link_url", "link_text",
        "http_status", "reason",
        "wayback_url", "wayback_timestamp", "wayback_status",
    ]
    output_rows = []
    for r in results:
        if r.get("http_status", "") not in DEAD_STATUSES:
            continue
        url = r["link_url"]
        wb = wayback_results.get(url, {})
        output_rows.append({
            "section": r["section"],
            "page_title": r["page_title"],
            "page_url": r["page_url"],
            "source_file": r["source_file"],
            "link_url": url,
            "link_text": r["link_text"],
            "http_status": r["http_status"],
            "reason": r["reason"],
            "wayback_url": wb.get("wayback_url", ""),
            "wayback_timestamp": wb.get("wayback_timestamp", ""),
            "wayback_status": wb.get("wayback_status", ""),
        })

    with open(WAYBACK_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    found = sum(1 for r in output_rows if r["wayback_status"] == "found")
    not_archived = sum(1 for r in output_rows if r["wayback_status"] == "not_archived")
    print(f"\nResults written to {WAYBACK_CSV}")
    print(f"Total dead link references: {len(output_rows)}")
    print(f"Wayback snapshot found:     {found}")
    print(f"Not archived:               {not_archived}")


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(description="External link checker for teachinghistory.org")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("extract", help="Build external link inventory from content files")

    check_parser = sub.add_parser("check", help="Check URLs from inventory")
    check_parser.add_argument("--resume", action="store_true", help="Skip already-checked URLs")
    check_parser.add_argument("--limit", type=int, default=None, help="Max URLs to check this run")

    wayback_parser = sub.add_parser("wayback", help="Look up Wayback Machine snapshots for dead links")
    wayback_parser.add_argument("--resume", action="store_true", help="Skip already-looked-up URLs")
    wayback_parser.add_argument("--limit", type=int, default=None, help="Max URLs to look up this run")

    args = parser.parse_args()
    if args.command == "extract":
        run_extract()
    elif args.command == "check":
        run_check(resume=args.resume, limit=args.limit)
    elif args.command == "wayback":
        run_wayback(resume=args.resume, limit=args.limit)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
