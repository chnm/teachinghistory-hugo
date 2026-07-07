# Link Review Triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `utils/link_checker.py` to produce a review spreadsheet (`link_review_master.csv` + `.xlsx`) classifying every external link for Step 1 (broken-ness) and Step 1.5 (bulk-delete bucket) decisions, without mutating any content.

**Architecture:** Add document-context capture to the existing `extract` phase, a `recheck` subcommand that re-verifies ambiguous 403s with a browser-like User-Agent, and a `classify` subcommand that joins inventory + check results + wayback data into a single master sheet with derived triage columns. All derivation logic lives in small pure functions that are unit-tested without the network; the network re-check is verified with a stub session and manual spot-checks.

**Tech Stack:** Python 3.10+, `uv` single-file script (inline dependency block), `requests`, `beautifulsoup4`, `pyyaml`, `openpyxl` (new). No web framework, no database.

## Global Constraints

- `utils/link_checker.py` is a `uv` single-file script — new third-party imports MUST be added to the inline `# /// script` dependency block at the top. (Add `openpyxl`.)
- Python floor: `requires-python = ">=3.10"` (keep the existing type-hint style, e.g. `int | None`).
- This build MUST NOT modify any content under `teachinghistory-website/content/`. It only reads content and writes CSV/XLSX into `utils/`.
- Follow the existing CSV-handoff pattern: each phase reads/writes CSVs in `utils/` (`INVENTORY_CSV`, `RESULTS_CSV`, `WAYBACK_CSV`).
- Preserve `url` frontmatter and all existing content — never write to content files.
- Conventional Commits (`feat:`, `docs:`, `test:`, `refactor:`).
- Tests run with:
  `uv run --with pytest --with requests --with beautifulsoup4 --with pyyaml --with openpyxl pytest utils/tests/test_link_review.py -v`
- Bulk-delete precondition: a link is a `bulk_delete_candidate` when it belongs to ANY bucket (`bucket != "none"`), regardless of HTTP status. Status is shown in the sheet for the human to decide.
- `broken_category` value set (exactly these six): `A`, `C-candidate`, `B?`, `live`, `needs-human`, `blocked-unknown`.

---

## File Structure

- **Modify:** `utils/link_checker.py`
  - Add pure helpers: heading indexing, bibliography/caption detection, bare-URL-aware link extraction, redirect classification, category/bucket/confidence/action derivation.
  - Enrich `run_extract` to write context columns; make `run_check`'s writer tolerate extra inventory columns.
  - Add `run_recheck` and `run_classify` plus their CLI subparsers and xlsx writer.
- **Create:** `utils/tests/test_link_review.py` — unit tests for all pure functions and a stub-session test for the User-Agent plumbing.
- **Modify:** `CLAUDE.md` and `AGENTS.md` — document the new `recheck`/`classify` commands and the master-sheet output.

The test file imports the script by file path (it has a hyphen-free name but lives beside a `# ///` header), using `importlib`, so it works regardless of the current working directory.

---

## Task 1: Document-context extraction

Capture, for each external link, the nearest heading, whether it sits under a bibliography-style heading, a low-confidence caption flag, and whether it's a real hyperlink or a written-out bare URL (bare URLs are newly captured — Step 1.5 explicitly covers "written out urls").

**Files:**
- Modify: `utils/link_checker.py` (add helpers near the Extract phase; update `run_extract`; adjust `run_check` writer)
- Test: `utils/tests/test_link_review.py`

**Interfaces:**
- Produces:
  - `build_heading_index(text: str) -> list[tuple[int, str]]`
  - `heading_at(index: list[tuple[int, str]], pos: int) -> str`
  - `normalize_heading(h: str) -> str`
  - `is_bibliography_heading(h: str) -> bool`
  - `looks_like_caption(line: str) -> bool`
  - `extract_links_with_context(text: str) -> list[dict]` — each dict has keys `link_url, link_text, link_kind, doc_heading, in_bibliography, in_caption`
  - Enriched `INVENTORY_CSV` columns: `section, page_title, page_url, source_file, link_url, link_text, link_kind, doc_heading, in_bibliography, in_caption`

- [ ] **Step 1: Write the failing tests**

Create `utils/tests/test_link_review.py`:

```python
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "link_checker", Path(__file__).resolve().parent.parent / "link_checker.py"
)
lc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lc)


def test_normalize_heading_strips_punctuation_and_case():
    assert lc.normalize_heading("## For Further Reading") == "for further reading"
    assert lc.normalize_heading("References:") == "references"


def test_is_bibliography_heading_whole_match_only():
    assert lc.is_bibliography_heading("For Further Reading") is True
    assert lc.is_bibliography_heading("Bibliography") is True
    assert lc.is_bibliography_heading("References") is True
    # Must NOT match partial/compound headings:
    assert lc.is_bibliography_heading("Sources of Unity") is False
    assert lc.is_bibliography_heading("Sources and Teaching Models") is False


def test_heading_at_returns_nearest_preceding_heading():
    text = "# Intro\nbody\n## For Further Reading\n- a link here\n"
    idx = lc.build_heading_index(text)
    pos = text.index("a link here")
    assert lc.heading_at(idx, pos) == "For Further Reading"
    pos_intro = text.index("body")
    assert lc.heading_at(idx, pos_intro) == "Intro"


def test_looks_like_caption():
    assert lc.looks_like_caption("![poster](/img/x.jpg) A poster") is True
    assert lc.looks_like_caption("Courtesy of the Library of Congress, 1973") is True
    assert lc.looks_like_caption("Just a normal sentence with a point.") is False


def test_extract_links_with_context_classifies_kind_and_bucket_context():
    text = (
        "## For Further Reading\n"
        "See [the guide](https://example.org/guide) and also\n"
        "March to Wounded Knee, Library of Congress, https://www.loc.gov/item/2016648085/\n"
    )
    rows = lc.extract_links_with_context(text)
    by_url = {r["link_url"]: r for r in rows}

    guide = by_url["https://example.org/guide"]
    assert guide["link_kind"] == "hyperlink"
    assert guide["in_bibliography"] is True

    loc = by_url["https://www.loc.gov/item/2016648085/"]
    assert loc["link_kind"] == "bare_url"
    assert loc["in_bibliography"] is True
    assert loc["in_caption"] is True  # "Library of Congress" hint on the line
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest --with requests --with beautifulsoup4 --with pyyaml --with openpyxl pytest utils/tests/test_link_review.py -v`
Expected: FAIL — `AttributeError: module 'link_checker' has no attribute 'normalize_heading'`.

- [ ] **Step 3: Implement the pure helpers**

In `utils/link_checker.py`, in the `# --- Extract phase ---` region (after `extract_links`), add:

```python
BIBLIOGRAPHY_HEADINGS = {
    "for further reading", "further reading", "bibliography",
    "references", "works cited", "further resources",
    "related resources", "sources", "notes", "endnotes",
}

CAPTION_HINTS = re.compile(
    r"(library of congress|courtesy of|courtesy,|source:|photo:|image:|"
    r"credit:|national archives|smithsonian)",
    re.IGNORECASE,
)


def build_heading_index(text: str) -> list[tuple[int, str]]:
    """List of (char_offset, heading_text) for each ATX heading, in order."""
    index = []
    offset = 0
    for line in text.splitlines(keepends=True):
        m = re.match(r"\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$", line)
        if m:
            index.append((offset, m.group(1).strip()))
        offset += len(line)
    return index


def heading_at(index: list[tuple[int, str]], pos: int) -> str:
    """Nearest heading at or before character offset `pos` ("" if none)."""
    current = ""
    for off, head in index:
        if off <= pos:
            current = head
        else:
            break
    return current


def normalize_heading(h: str) -> str:
    stripped = re.sub(r"^#+\s*", "", h).strip()
    return re.sub(r"[^a-z0-9 ]", "", stripped.lower()).strip()


def is_bibliography_heading(h: str) -> bool:
    return normalize_heading(h) in BIBLIOGRAPHY_HEADINGS


def looks_like_caption(line: str) -> bool:
    if "![" in line:
        return True
    return bool(CAPTION_HINTS.search(line))


def _line_at(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end == -1:
        end = len(text)
    return text[start:end]


def extract_links_with_context(text: str) -> list[dict]:
    """Extract links with document context. Captures markdown links, HTML
    anchors, and written-out bare URLs (marked link_kind='bare_url')."""
    index = build_heading_index(text)
    spans: list[tuple[int, int]] = []
    results: list[dict] = []

    def add(pos: int, url: str, link_text: str, kind: str) -> None:
        heading = heading_at(index, pos)
        results.append({
            "link_url": url,
            "link_text": link_text,
            "link_kind": kind,
            "doc_heading": heading,
            "in_bibliography": is_bibliography_heading(heading),
            "in_caption": looks_like_caption(_line_at(text, pos)),
        })

    for m in re.finditer(r"\[([^\]]*)\]\(([^)]+)\)", text):
        spans.append((m.start(), m.end()))
        add(m.start(), m.group(2).strip(), m.group(1).strip(), "hyperlink")

    for m in re.finditer(
        r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        text, re.IGNORECASE | re.DOTALL,
    ):
        spans.append((m.start(), m.end()))
        link_text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        add(m.start(), m.group(1).strip(), link_text, "hyperlink")

    for m in re.finditer(r"https?://[^\s<>)\"'\]]+", text):
        if any(s <= m.start() < e for s, e in spans):
            continue  # already captured inside a markdown/HTML link
        url = m.group(0).rstrip(".,;")
        add(m.start(), url, url, "bare_url")

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pytest --with requests --with beautifulsoup4 --with pyyaml --with openpyxl pytest utils/tests/test_link_review.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Wire context columns into `run_extract`**

Replace the link loop and `fieldnames` in `run_extract` (currently around lines 124–148) so it uses `extract_links_with_context` and writes the new columns:

```python
        for link in extract_links_with_context(text):
            url = link["link_url"]
            if is_external(url):
                rows.append({
                    "section": section,
                    "page_title": page_title,
                    "page_url": page_url,
                    "source_file": str(rel_path),
                    "link_url": url,
                    "link_text": link["link_text"],
                    "link_kind": link["link_kind"],
                    "doc_heading": link["doc_heading"],
                    "in_bibliography": link["in_bibliography"],
                    "in_caption": link["in_caption"],
                })
```

And update the writer's `fieldnames`:

```python
    fieldnames = [
        "section", "page_title", "page_url", "source_file",
        "link_url", "link_text", "link_kind",
        "doc_heading", "in_bibliography", "in_caption",
    ]
```

- [ ] **Step 6: Make `run_check` tolerate the new inventory columns**

`run_check` spreads full inventory rows into its output (`{**row, ...}`) but writes with a fixed `fieldnames` list, which makes `csv.DictWriter` raise on the new keys. Add `extrasaction="ignore"` to that writer (currently around line 304):

```python
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
```

- [ ] **Step 7: Smoke-test extract against real content**

Run: `uv run utils/link_checker.py extract`
Expected: completes; then verify context columns populate:
`python3 -c "import csv; rows=list(csv.DictReader(open('utils/link_inventory.csv'))); print(sum(r['in_bibliography']=='True' for r in rows), 'in-biblio;', sum(r['link_kind']=='bare_url' for r in rows), 'bare urls')"`
Expected: a non-zero in-bibliography count (roughly matches ~140 files) and some bare URLs.

- [ ] **Step 8: Commit**

```bash
git add utils/link_checker.py utils/tests/test_link_review.py utils/link_inventory.csv
git commit -m "feat: capture document context (heading, bibliography, caption, link kind) in link extract"
```

---

## Task 2: `recheck` subcommand for ambiguous 403s

Re-verify `403` responses with a browser-like User-Agent, since many are WAF bot-blocks rather than dead links.

**Files:**
- Modify: `utils/link_checker.py` (parametrize `check_url`; add `BROWSER_UA`, `is_reverifiable_status`, `run_recheck`, CLI subparser)
- Test: `utils/tests/test_link_review.py`

**Interfaces:**
- Consumes: `check_url(url, session)` from the existing script; `RESULTS_CSV`.
- Produces:
  - `BROWSER_UA: str`
  - `check_url(url: str, session, user_agent: str = USER_AGENT) -> dict` (new optional param)
  - `is_reverifiable_status(status: str) -> bool`
  - `run_recheck(limit: int | None = None) -> None` — re-checks `403` URLs in `RESULTS_CSV` and rewrites it in place.

- [ ] **Step 1: Write the failing tests**

Append to `utils/tests/test_link_review.py`:

```python
def test_is_reverifiable_status():
    assert lc.is_reverifiable_status("403") is True
    assert lc.is_reverifiable_status("404") is False
    assert lc.is_reverifiable_status("200") is False


class _StubResp:
    def __init__(self):
        self.status_code = 200
        self.url = "https://example.org/"
        self.headers = {"content-type": "text/html"}
        self.text = "<title>Fine</title>"


class _StubSession:
    def __init__(self):
        self.last_headers = None

    def get(self, url, timeout, allow_redirects, headers):
        self.last_headers = headers
        return _StubResp()


def test_check_url_uses_supplied_user_agent():
    session = _StubSession()
    lc.check_url("https://example.org/", session, user_agent=lc.BROWSER_UA)
    assert session.last_headers["User-Agent"] == lc.BROWSER_UA
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest --with requests --with beautifulsoup4 --with pyyaml --with openpyxl pytest utils/tests/test_link_review.py -v`
Expected: FAIL — `AttributeError: module 'link_checker' has no attribute 'is_reverifiable_status'`.

- [ ] **Step 3: Add `BROWSER_UA` and parametrize `check_url`**

Near the other constants (after `USER_AGENT`, ~line 62):

```python
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
```

Change the `check_url` signature and the header it sends (the `session.get(...)` call around line 169):

```python
def check_url(url: str, session: requests.Session, user_agent: str = USER_AGENT) -> dict:
```

```python
        resp = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            headers={"User-Agent": user_agent},
        )
```

- [ ] **Step 4: Add `is_reverifiable_status` and `run_recheck`**

Add after `run_check`:

```python
def is_reverifiable_status(status: str) -> bool:
    """Statuses worth re-checking with a browser UA (bot-block false positives)."""
    return str(status) == "403"


def run_recheck(limit: int | None = None):
    """Re-check 403 URLs in RESULTS_CSV with a browser-like User-Agent."""
    if not RESULTS_CSV.exists():
        print(f"No results found at {RESULTS_CSV}. Run 'check' first.")
        sys.exit(1)

    with open(RESULTS_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(csv.DictReader(open(RESULTS_CSV, encoding="utf-8")).fieldnames)

    target_urls = sorted({
        r["link_url"] for r in rows if is_reverifiable_status(r.get("http_status", ""))
    })
    if limit:
        target_urls = target_urls[:limit]
    print(f"Re-checking {len(target_urls)} URLs (403) with browser User-Agent...")

    session = requests.Session()
    updated: dict[str, dict] = {}
    for i, url in enumerate(target_urls, 1):
        if i % 50 == 0 or i == 1:
            print(f"  [{i}/{len(target_urls)}] rechecking {url[:80]}...")
        updated[url] = check_url(url, session, user_agent=BROWSER_UA)
        time.sleep(REQUEST_DELAY)

    changed = 0
    for r in rows:
        u = r["link_url"]
        if u in updated:
            res = updated[u]
            if str(r["http_status"]) != str(res["http_status"]):
                changed += 1
            r["http_status"] = res["http_status"]
            r["final_url"] = res["final_url"]
            r["remote_title"] = res["remote_title"]
            r["redirect_domain_changed"] = res["redirect_domain_changed"]
            r["needs_review"] = res["needs_review"]
            r["reason"] = res["reason"]

    with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nRewrote {RESULTS_CSV}. {changed} rows changed status after re-check.")
```

- [ ] **Step 5: Wire the CLI subparser**

In `main()`, add after the `wayback_parser` block:

```python
    recheck_parser = sub.add_parser("recheck", help="Re-check 403 URLs with a browser User-Agent")
    recheck_parser.add_argument("--limit", type=int, default=None, help="Max URLs to re-check")
```

And in the dispatch chain:

```python
    elif args.command == "recheck":
        run_recheck(limit=args.limit)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run --with pytest --with requests --with beautifulsoup4 --with pyyaml --with openpyxl pytest utils/tests/test_link_review.py -v`
Expected: PASS (8 passed).

- [ ] **Step 7: Manual verification against a known bot-blocked URL**

Run: `uv run utils/link_checker.py recheck --limit 25`
Expected: prints a "N rows changed status" count; spot-check that at least some 403s resolved to 200.

- [ ] **Step 8: Commit**

```bash
git add utils/link_checker.py utils/tests/test_link_review.py utils/link_results.csv
git commit -m "feat: add recheck subcommand to re-verify 403s with browser user-agent"
```

---

## Task 3: `classify` subcommand and master CSV

Derive the triage columns and join inventory + results + wayback into `link_review_master.csv`.

**Files:**
- Modify: `utils/link_checker.py` (add derivation helpers, `run_classify`, CLI subparser; add `MASTER_CSV` path)
- Test: `utils/tests/test_link_review.py`

**Interfaces:**
- Consumes: `INVENTORY_CSV` (context cols from Task 1), `RESULTS_CSV` (status cols, post-recheck), `WAYBACK_CSV`, `DEAD_STATUSES`, `SUSPICIOUS_TITLE_WORDS`, `BOOKSELLER_DOMAINS`.
- Produces:
  - `BOOKSELLER_DOMAINS: set[str]`
  - `classify_redirect(orig_url: str, final_url: str) -> str` → `"none" | "benign" | "substantive"`
  - `is_bookseller(url: str) -> bool`
  - `bucket_for(url: str, in_bibliography: bool, in_caption: bool) -> str` → `"bookseller" | "bibliography" | "caption_maybe" | "none"`
  - `broken_category(http_status: str, redirect_kind: str, remote_title: str) -> str`
  - `confidence_for(category: str, bucket: str) -> str` → `"high" | "medium" | "low"`
  - `suggested_action(category: str, bucket: str, wayback_status: str) -> str`
  - `run_classify() -> None` → writes `MASTER_CSV`
  - `MASTER_CSV = OUTPUT_DIR / "link_review_master.csv"`

- [ ] **Step 1: Write the failing tests**

Append to `utils/tests/test_link_review.py`:

```python
def test_classify_redirect():
    assert lc.classify_redirect("http://x.org/a", "https://x.org/a") == "benign"
    assert lc.classify_redirect("http://x.org/a", "http://www.x.org/a/") == "benign"
    assert lc.classify_redirect("http://x.org/a", "https://other.com/z") == "substantive"
    assert lc.classify_redirect("http://x.org/a", "") == "none"


def test_is_bookseller_and_bucket_priority():
    assert lc.is_bookseller("https://www.amazon.com/dp/123") is True
    assert lc.is_bookseller("https://books.google.com/books?id=1") is True
    assert lc.is_bookseller("https://loc.gov/item/1") is False
    # Bookseller wins even when under a bibliography heading:
    assert lc.bucket_for("https://amazon.com/x", True, False) == "bookseller"
    assert lc.bucket_for("https://loc.gov/x", True, False) == "bibliography"
    assert lc.bucket_for("https://loc.gov/x", False, True) == "caption_maybe"
    assert lc.bucket_for("https://loc.gov/x", False, False) == "none"


def test_broken_category():
    assert lc.broken_category("404", "none", "") == "A"
    assert lc.broken_category("CONN_ERROR", "none", "") == "A"
    assert lc.broken_category("403", "none", "") == "blocked-unknown"
    assert lc.broken_category("200", "substantive", "Padlet") == "C-candidate"
    assert lc.broken_category("200", "none", "404 Page Not Found") == "B?"
    assert lc.broken_category("200", "benign", "Real Article Title") == "live"
    assert lc.broken_category("429", "none", "") == "needs-human"


def test_confidence_and_action():
    assert lc.confidence_for("A", "none") == "high"
    assert lc.confidence_for("C-candidate", "none") == "medium"
    assert lc.confidence_for("needs-human", "caption_maybe") == "low"

    assert lc.suggested_action("A", "bookseller", "not_archived") == "bulk-unlink"
    assert lc.suggested_action("A", "none", "found") == "salvage-wayback"
    assert lc.suggested_action("C-candidate", "none", "not_archived") == "needs-subjective-review"
    assert lc.suggested_action("live", "none", "") == "ok"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest --with requests --with beautifulsoup4 --with pyyaml --with openpyxl pytest utils/tests/test_link_review.py -v`
Expected: FAIL — `AttributeError: module 'link_checker' has no attribute 'classify_redirect'`.

- [ ] **Step 3: Add derivation helpers**

Add a `# --- Classify phase ---` region before `# --- CLI ---`:

```python
# --- Classify phase ---

MASTER_CSV = OUTPUT_DIR / "link_review_master.csv"
MASTER_XLSX = OUTPUT_DIR / "link_review_master.xlsx"

BOOKSELLER_DOMAINS = {
    "amazon.", "barnesandnoble.", "bn.com", "abebooks.",
    "powells.", "bookshop.org", "thriftbooks.", "alibris.",
    "books.google.",
}


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def classify_redirect(orig_url: str, final_url: str) -> str:
    """'none' if no redirect, 'benign' if same host, 'substantive' if host changed."""
    if not final_url or final_url == orig_url:
        return "none"
    if _host(orig_url) == _host(final_url):
        return "benign"
    return "substantive"


def is_bookseller(url: str) -> bool:
    host = _host(url)
    return any(token in host for token in BOOKSELLER_DOMAINS)


def bucket_for(url: str, in_bibliography: bool, in_caption: bool) -> str:
    if is_bookseller(url):
        return "bookseller"
    if in_bibliography:
        return "bibliography"
    if in_caption:
        return "caption_maybe"
    return "none"


def broken_category(http_status: str, redirect_kind: str, remote_title: str) -> str:
    status = str(http_status)
    if status in DEAD_STATUSES:
        return "A"
    if status == "403":
        return "blocked-unknown"
    if status.startswith("2"):
        title = (remote_title or "").lower()
        if any(w in title for w in SUSPICIOUS_TITLE_WORDS):
            return "B?"
        if redirect_kind == "substantive":
            return "C-candidate"
        return "live"
    return "needs-human"


def confidence_for(category: str, bucket: str) -> str:
    if category == "A" or bucket == "bookseller" or category == "live":
        return "high"
    if category in ("C-candidate", "B?") or bucket == "bibliography":
        return "medium"
    return "low"


def suggested_action(category: str, bucket: str, wayback_status: str) -> str:
    if bucket != "none":
        return "bulk-unlink"
    if category == "A" and wayback_status == "found":
        return "salvage-wayback"
    if category in ("A", "C-candidate", "B?", "blocked-unknown"):
        return "needs-subjective-review"
    return "ok"
```

Note: `DEAD_STATUSES` and `SUSPICIOUS_TITLE_WORDS` are already defined earlier in the file; `broken_category` and `suggested_action` reference them directly.

- [ ] **Step 4: Run helper tests to verify they pass**

Run: `uv run --with pytest --with requests --with beautifulsoup4 --with pyyaml --with openpyxl pytest utils/tests/test_link_review.py -v`
Expected: PASS (12 passed).

- [ ] **Step 5: Add `run_classify` (CSV only for now)**

Add after the helpers:

```python
MASTER_FIELDNAMES = [
    "section", "page_title", "page_url", "source_file",
    "link_url", "link_text", "link_kind",
    "doc_heading", "in_bibliography", "in_caption",
    "http_status", "final_url", "redirect_kind", "remote_title",
    "broken_category", "bucket", "bulk_delete_candidate",
    "confidence", "suggested_action",
    "wayback_url", "wayback_status",
]


def _load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_classify():
    """Join inventory + results + wayback into the master review sheet."""
    inventory = _load_csv(INVENTORY_CSV)
    if not inventory:
        print(f"No inventory found at {INVENTORY_CSV}. Run 'extract' first.")
        sys.exit(1)

    results = {(r["source_file"], r["link_url"]): r for r in _load_csv(RESULTS_CSV)}
    wayback = {(r["source_file"], r["link_url"]): r for r in _load_csv(WAYBACK_CSV)}

    rows = []
    for inv in inventory:
        key = (inv["source_file"], inv["link_url"])
        res = results.get(key, {})
        wb = wayback.get(key, {})

        http_status = res.get("http_status", "")
        final_url = res.get("final_url", "")
        remote_title = res.get("remote_title", "")
        in_bib = str(inv.get("in_bibliography", "")) == "True"
        in_cap = str(inv.get("in_caption", "")) == "True"

        redirect_kind = classify_redirect(inv["link_url"], final_url)
        bucket = bucket_for(inv["link_url"], in_bib, in_cap)
        category = broken_category(http_status, redirect_kind, remote_title)
        wb_status = wb.get("wayback_status", "")

        rows.append({
            "section": inv["section"],
            "page_title": inv["page_title"],
            "page_url": inv["page_url"],
            "source_file": inv["source_file"],
            "link_url": inv["link_url"],
            "link_text": inv["link_text"],
            "link_kind": inv.get("link_kind", ""),
            "doc_heading": inv.get("doc_heading", ""),
            "in_bibliography": in_bib,
            "in_caption": in_cap,
            "http_status": http_status,
            "final_url": final_url,
            "redirect_kind": redirect_kind,
            "remote_title": remote_title,
            "broken_category": category,
            "bucket": bucket,
            "bulk_delete_candidate": bucket != "none",
            "confidence": confidence_for(category, bucket),
            "suggested_action": suggested_action(category, bucket, wb_status),
            "wayback_url": wb.get("wayback_url", ""),
            "wayback_status": wb_status,
        })

    with open(MASTER_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MASTER_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    n_candidates = sum(1 for r in rows if r["bulk_delete_candidate"])
    print(f"\nWrote {MASTER_CSV} ({len(rows)} rows).")
    print(f"Bulk-delete candidates: {n_candidates}")
    import collections
    cats = collections.Counter(r["broken_category"] for r in rows)
    for cat, n in cats.most_common():
        print(f"  {cat}: {n}")
```

- [ ] **Step 6: Wire the CLI subparser**

In `main()`, add:

```python
    sub.add_parser("classify", help="Join inventory + results + wayback into the master review sheet")
```

And in the dispatch chain:

```python
    elif args.command == "classify":
        run_classify()
```

- [ ] **Step 7: Smoke-test classify against real data**

Run: `uv run utils/link_checker.py classify`
Expected: prints row count, a bulk-delete-candidate count, and a category breakdown. Verify:
`python3 -c "import csv,collections; c=collections.Counter(r['bucket'] for r in csv.DictReader(open('utils/link_review_master.csv'))); print(c)"`
Expected: `bookseller`, `bibliography`, `caption_maybe`, `none` counts roughly matching feasibility numbers (bookseller ~175, bibliography in the low hundreds).

- [ ] **Step 8: Commit**

```bash
git add utils/link_checker.py utils/tests/test_link_review.py utils/link_review_master.csv
git commit -m "feat: add classify subcommand producing the master link review sheet"
```

---

## Task 4: XLSX output and documentation

Emit a human-friendly `.xlsx` alongside the CSV and document the new workflow.

**Files:**
- Modify: `utils/link_checker.py` (inline deps: add `openpyxl`; add `write_master_xlsx`; call it from `run_classify`)
- Modify: `CLAUDE.md`, `AGENTS.md`
- Test: `utils/tests/test_link_review.py`

**Interfaces:**
- Consumes: `MASTER_FIELDNAMES`, `MASTER_XLSX`, the rows built in `run_classify`.
- Produces: `write_master_xlsx(rows: list[dict], path: Path) -> None`

- [ ] **Step 1: Add `openpyxl` to the inline dependency block**

Edit the `# /// script` header at the top of `utils/link_checker.py`:

```python
# dependencies = [
#     "requests",
#     "beautifulsoup4",
#     "pyyaml",
#     "openpyxl",
# ]
```

- [ ] **Step 2: Write the failing test**

Append to `utils/tests/test_link_review.py`:

```python
def test_write_master_xlsx(tmp_path):
    import openpyxl
    rows = [{k: "" for k in lc.MASTER_FIELDNAMES}]
    rows[0]["link_url"] = "https://example.org/x"
    rows[0]["bucket"] = "bookseller"
    out = tmp_path / "sheet.xlsx"
    lc.write_master_xlsx(rows, out)
    assert out.exists()
    wb = openpyxl.load_workbook(out)
    ws = wb.active
    assert [c.value for c in ws[1]] == lc.MASTER_FIELDNAMES
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref is not None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run --with pytest --with requests --with beautifulsoup4 --with pyyaml --with openpyxl pytest utils/tests/test_link_review.py::test_write_master_xlsx -v`
Expected: FAIL — `AttributeError: module 'link_checker' has no attribute 'write_master_xlsx'`.

- [ ] **Step 4: Implement `write_master_xlsx`**

Add near `run_classify` in the Classify region:

```python
def write_master_xlsx(rows: list[dict], path: Path) -> None:
    """Write the master sheet as .xlsx with a frozen header and autofilter."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "link_review"
    ws.append(MASTER_FIELDNAMES)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([row.get(col, "") for col in MASTER_FIELDNAMES])

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{ws.cell(row=1, column=len(MASTER_FIELDNAMES)).column_letter}{ws.max_row}"

    widths = {"page_title": 40, "source_file": 40, "link_url": 50,
              "link_text": 30, "final_url": 40, "remote_title": 30}
    for i, col in enumerate(MASTER_FIELDNAMES, 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = widths.get(col, 16)

    wb.save(path)
```

- [ ] **Step 5: Call it from `run_classify`**

At the end of `run_classify`, after writing the CSV (after the category breakdown loop), add:

```python
    write_master_xlsx(rows, MASTER_XLSX)
    print(f"Wrote {MASTER_XLSX}")
```

- [ ] **Step 6: Run the full test suite**

Run: `uv run --with pytest --with requests --with beautifulsoup4 --with pyyaml --with openpyxl pytest utils/tests/test_link_review.py -v`
Expected: PASS (13 passed).

- [ ] **Step 7: Regenerate and eyeball the xlsx**

Run: `uv run utils/link_checker.py classify`
Expected: writes both `utils/link_review_master.csv` and `utils/link_review_master.xlsx`. Open the xlsx, confirm frozen header + autofilter, and filter `bulk_delete_candidate = TRUE` and `broken_category = A`.

- [ ] **Step 8: Document the new workflow**

In `CLAUDE.md`, under the "External Link Checker" section, update the command list to include the full pipeline:

```markdown
uv run utils/link_checker.py extract          # Build link inventory (with document context)
uv run utils/link_checker.py check --resume   # Check HTTP status of each URL
uv run utils/link_checker.py recheck          # Re-verify 403s with a browser user-agent
uv run utils/link_checker.py wayback --resume # Look up Wayback snapshots for dead links
uv run utils/link_checker.py classify         # Build the master review sheet (CSV + XLSX)
```

And add `link_review_master.csv`/`link_review_master.xlsx` to the list of output files.

In `AGENTS.md`, add a one-line pointer to the same pipeline where the link checker is mentioned (if referenced).

- [ ] **Step 9: Commit**

```bash
git add utils/link_checker.py utils/tests/test_link_review.py CLAUDE.md AGENTS.md utils/link_review_master.csv utils/link_review_master.xlsx
git commit -m "feat: emit xlsx review sheet and document link triage pipeline"
```

---

## Self-Review

**Spec coverage:**
- Stage 1 (enrich extract with `doc_heading`, `in_bibliography`, `in_caption`, `link_kind`) → Task 1. ✓ (Bare-URL capture added, per spec's `bare_url` link_kind and Step 1.5 "written out urls".)
- Stage 2 (`recheck` 403s with browser UA; benign-vs-substantive redirect) → Task 2 (recheck) + Task 3 (`classify_redirect` derives `redirect_kind`). ✓ Note: redirect classification is derived in `classify` (where all derivations live) rather than persisted during recheck — same output column, cleaner separation.
- Stage 3 (`classify`: `broken_category`, `bucket`, `bulk_delete_candidate`, `confidence`, `suggested_action`, wayback join) → Task 3. ✓ All six `broken_category` values covered by tests.
- Stage 4 (master CSV + xlsx with frozen header/autofilter) → Task 3 (CSV) + Task 4 (xlsx). ✓
- Column set matches the spec's final list exactly. ✓
- "No content mutation" constraint → honored; only `utils/` CSV/XLSX are written. ✓
- Decision 2 (in-bucket alone qualifies) → `bulk_delete_candidate = bucket != "none"`, tested. ✓

**Placeholder scan:** No TBD/TODO; every code step contains complete code. ✓

**Type consistency:** `broken_category`/`bucket`/`redirect_kind`/`confidence`/`suggested_action` string values are identical between their producing helpers (Task 3) and the tests and `run_classify` consumer. `MASTER_FIELDNAMES` defined once and reused by both the CSV writer and `write_master_xlsx`. `check_url`'s new `user_agent` param is backward-compatible (defaults to `USER_AGENT`), so existing `run_check`/`run_recheck` calls stay valid. ✓
