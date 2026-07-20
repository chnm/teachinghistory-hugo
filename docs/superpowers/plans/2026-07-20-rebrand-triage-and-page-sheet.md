# Rebrand Triage Refinement & Page-Level Sheet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-triage the 500 `C-candidate` (rebranded) links into probably-broken / probably-fine / needs-human verdicts, and add a one-row-per-page derivative sheet for bulk page-deletion decisions.

**Architecture:** All new logic is deterministic post-processing inside `utils/link_checker.py` — no network calls, no new dependencies. Part 1 adds pure verdict helpers wired into the existing `classify` stage (3 new master-sheet columns + verdict-aware `suggested_action`). Part 2 adds a `pages` subcommand that reads `link_review_master.csv` and writes `link_review_pages.csv`/`.xlsx`.

**Tech Stack:** Python 3.10+ single-file `uv` script (PEP 723 inline deps: requests, beautifulsoup4, pyyaml, openpyxl). Tests: pytest in `utils/tests/test_link_review.py`.

**Spec:** `docs/superpowers/specs/2026-07-20-rebrand-triage-and-page-sheet-design.md`

## Global Constraints

- **No new dependencies.** The PEP 723 block in `utils/link_checker.py` stays exactly: `requests`, `beautifulsoup4`, `pyyaml`, `openpyxl`.
- **No network in `classify` or `pages`.** Both are pure joins/aggregations over existing CSVs.
- **No content mutation.** Only CSV/XLSX outputs under `utils/`. The `apply` step is out of scope.
- **Test command (used in every task):**
  `uv run --with pytest --with requests --with beautifulsoup4 --with pyyaml --with openpyxl pytest utils/tests/test_link_review.py -v`
- **Column names verbatim from the spec:** master additions `final_is_homepage`, `history_signal`, `rebrand_verdict` (appended at the end of `MASTER_FIELDNAMES`); verdict values `probably-broken`, `probably-fine`, `needs-human`; new suggested actions `update-to-final-url`, `remove-or-replace`; page action values `delete-page-candidate`, `salvage-wayback`, `fix-links-only`.
- **Existing behavior unchanged** for non-C-candidate rows and for bucketed rows (`bulk-unlink` still wins over any verdict).
- **Branch:** `fix/dead-links`. Conventional Commits (`feat:`, `test:`, `docs:`, `chore:`).
- **Expected real-data counts** (verified by prototype, must match after implementation): C-candidate verdicts 147 probably-broken / 293 probably-fine / 60 needs-human; page sheet 1,206 rows.

---

### Task 1: Rebrand verdict helpers

Pure functions only — no wiring yet. `source_file` paths in the sheet look like `history-content/website-reviews/foo-123.md`; final URLs like `https://rrchnm.org` (homepage-shaped) or `https://www.thirteen.org/wnet/historyofus/web07/segment2b.html` (deep link).

**Files:**
- Modify: `utils/link_checker.py` (insert after `classify_redirect`, currently ending at line 743)
- Test: `utils/tests/test_link_review.py`

**Interfaces:**
- Consumes: `urlparse` (already imported at top of link_checker.py).
- Produces (Task 2 depends on these exact signatures):
  - `is_homepage_url(url: str) -> bool`
  - `history_site_signal(remote_title: str, final_url: str) -> list[str]`
  - `rebrand_verdict(final_url: str, remote_title: str) -> str` — returns `"probably-broken" | "probably-fine" | "needs-human"`
  - Module constants `HOMEPAGE_PATHS: set[str]`, `HISTORY_VOCAB: list[str]`

- [ ] **Step 1: Write the failing tests**

Append to `utils/tests/test_link_review.py`:

```python
def test_is_homepage_url():
    assert lc.is_homepage_url("https://rrchnm.org") is True
    assert lc.is_homepage_url("https://rrchnm.org/") is True
    assert lc.is_homepage_url("https://example.org/index.html") is True
    assert lc.is_homepage_url("https://example.org/HOME/") is True
    assert lc.is_homepage_url("https://example.org/default.aspx") is True
    # Real paths and query strings are NOT homepages:
    assert lc.is_homepage_url("https://www.thirteen.org/wnet/historyofus/web07/segment2b.html") is False
    assert lc.is_homepage_url("https://example.org/?page_id=12") is False
    assert lc.is_homepage_url("https://www.c-span.org:443/series/?americanWriters") is False


def test_history_site_signal():
    # Title hit:
    assert "history" in lc.history_site_signal("A History of US", "https://x.com/a")
    # URL-only hit (row with no captured title):
    assert ".edu" in lc.history_site_signal("", "https://chnm.gmu.edu/page")
    # No hit:
    assert lc.history_site_signal("Casino online", "https://vn88.com/x") == []
    # Multiple hits all reported (sheet shows WHY something matched):
    hits = lc.history_site_signal("Museum of Education", "https://x.org/history/")
    assert set(hits) >= {"museum", "education", "history"}


def test_rebrand_verdict():
    # Homepage wins even when the title screams history (content gone, site survives):
    assert lc.rebrand_verdict("https://rrchnm.org", "Center for History and New Media") == "probably-broken"
    # Deep link + history signal:
    assert lc.rebrand_verdict(
        "https://www.thirteen.org/wnet/historyofus/web07.html",
        "Freedom: A History of US") == "probably-fine"
    # Deep link, no signal anywhere:
    assert lc.rebrand_verdict("https://vn88.com/casino", "Casino online") == "needs-human"
    # Missing title still matches on URL text:
    assert lc.rebrand_verdict("https://chnm.gmu.edu/loudountah/x", "") == "probably-fine"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest --with requests --with beautifulsoup4 --with pyyaml --with openpyxl pytest utils/tests/test_link_review.py -v`
Expected: the 3 new tests FAIL with `AttributeError: module 'link_checker' has no attribute 'is_homepage_url'` (etc.); the existing 12 PASS.

- [ ] **Step 3: Implement the helpers**

In `utils/link_checker.py`, insert after the `classify_redirect` function (before `is_bookseller`):

```python
HOMEPAGE_PATHS = {"", "index.html", "index.htm", "index.php", "home", "default.aspx"}

HISTORY_VOCAB = [
    "history", "historical", "primary source", "museum", "archive",
    "education", "teaching", "teacher", "library", "heritage",
    "humanities", "smithsonian", "social studies", "civics", "k-12",
    "learning", "lesson", "curriculum", "university", ".edu", ".gov",
]


def is_homepage_url(url: str) -> bool:
    """True when the URL points at a site root (trivial path, no query)."""
    parsed = urlparse(url)
    if parsed.query:
        return False
    return parsed.path.strip("/").lower() in HOMEPAGE_PATHS


def history_site_signal(remote_title: str, final_url: str) -> list[str]:
    """History/education vocabulary matched in the page title or final URL."""
    haystack = f"{remote_title or ''} {final_url or ''}".lower()
    return [word for word in HISTORY_VOCAB if word in haystack]


def rebrand_verdict(final_url: str, remote_title: str) -> str:
    """Triage a C-candidate: homepage redirect beats any history signal."""
    if is_homepage_url(final_url):
        return "probably-broken"
    if history_site_signal(remote_title, final_url):
        return "probably-fine"
    return "needs-human"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pytest --with requests --with beautifulsoup4 --with pyyaml --with openpyxl pytest utils/tests/test_link_review.py -v`
Expected: 15 PASS.

- [ ] **Step 5: Commit**

```bash
git add utils/link_checker.py utils/tests/test_link_review.py
git commit -m "feat: add rebrand verdict helpers (homepage + history-vocabulary checks)"
```

---

### Task 2: Wire verdicts into classify and regenerate the master sheet

**Files:**
- Modify: `utils/link_checker.py` — `suggested_action` (line ~785), `MASTER_FIELDNAMES` (line ~795), xlsx widths dict inside `write_master_xlsx` (line ~823), `run_classify` (line ~838)
- Test: `utils/tests/test_link_review.py`
- Regenerate: `utils/link_review_master.csv`, `utils/link_review_master.xlsx`

**Interfaces:**
- Consumes (from Task 1): `is_homepage_url(url)`, `history_site_signal(title, url)`, `rebrand_verdict(final_url, remote_title)`.
- Produces (Tasks 3–4 depend on these):
  - `suggested_action(category: str, bucket: str, wayback_status: str, rebrand_verdict: str = "") -> str` — new optional 4th parameter; existing 3-arg callers keep working.
  - Master sheet rows/CSV gain columns `final_is_homepage` (bool or `""`), `history_signal` (`"; "`-joined terms), `rebrand_verdict` (verdict or `""`), appended at the end of `MASTER_FIELDNAMES`.

- [ ] **Step 1: Write the failing test**

Append to `utils/tests/test_link_review.py`:

```python
def test_suggested_action_rebrand_verdicts():
    # probably-fine → mechanical repoint at the final URL:
    assert lc.suggested_action("C-candidate", "none", "",
                               rebrand_verdict="probably-fine") == "update-to-final-url"
    # probably-broken → wayback if archived, else remove/replace:
    assert lc.suggested_action("C-candidate", "none", "found",
                               rebrand_verdict="probably-broken") == "salvage-wayback"
    assert lc.suggested_action("C-candidate", "none", "not_archived",
                               rebrand_verdict="probably-broken") == "remove-or-replace"
    # needs-human keeps the old behavior:
    assert lc.suggested_action("C-candidate", "none", "",
                               rebrand_verdict="needs-human") == "needs-subjective-review"
    # Bucket still wins over any verdict:
    assert lc.suggested_action("C-candidate", "bookseller", "",
                               rebrand_verdict="probably-fine") == "bulk-unlink"
```

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `uv run --with pytest --with requests --with beautifulsoup4 --with pyyaml --with openpyxl pytest utils/tests/test_link_review.py -v`
Expected: `test_suggested_action_rebrand_verdicts` FAILS with `TypeError: suggested_action() got an unexpected keyword argument 'rebrand_verdict'`; all others PASS.

- [ ] **Step 3: Update `suggested_action`, `MASTER_FIELDNAMES`, xlsx widths, and `run_classify`**

Replace the `suggested_action` function with:

```python
def suggested_action(category: str, bucket: str, wayback_status: str,
                     rebrand_verdict: str = "") -> str:
    if bucket != "none":
        return "bulk-unlink"
    if category == "C-candidate":
        if rebrand_verdict == "probably-fine":
            return "update-to-final-url"
        if rebrand_verdict == "probably-broken":
            return "salvage-wayback" if wayback_status == "found" else "remove-or-replace"
        return "needs-subjective-review"
    if category == "A" and wayback_status == "found":
        return "salvage-wayback"
    if category in ("A", "B?", "blocked-unknown"):
        return "needs-subjective-review"
    return "ok"
```

Append three names to the end of `MASTER_FIELDNAMES`:

```python
MASTER_FIELDNAMES = [
    "section", "page_title", "page_url", "source_file",
    "link_url", "link_text", "link_kind",
    "doc_heading", "in_bibliography", "in_caption",
    "http_status", "final_url", "redirect_kind", "remote_title",
    "broken_category", "bucket", "bulk_delete_candidate",
    "confidence", "suggested_action",
    "wayback_url", "wayback_status",
    "final_is_homepage", "history_signal", "rebrand_verdict",
]
```

In `write_master_xlsx`, add `"history_signal": 30` to the `widths` dict.

In `run_classify`, after the line `wb_status = wb.get("wayback_status", "")`, add:

```python
        if category == "C-candidate":
            is_home = is_homepage_url(final_url)
            signal = history_site_signal(remote_title, final_url)
            verdict = rebrand_verdict(final_url, remote_title)
        else:
            is_home, signal, verdict = "", [], ""
```

In the `rows.append({...})` dict in `run_classify`, change the `suggested_action` line and add the three new columns at the end:

```python
            "suggested_action": suggested_action(category, bucket, wb_status, verdict),
            "wayback_url": wb.get("wayback_url", ""),
            "wayback_status": wb_status,
            "final_is_homepage": is_home,
            "history_signal": "; ".join(signal),
            "rebrand_verdict": verdict,
```

In the summary block of `run_classify` (after the `for cat, n in cats.most_common()` loop), add:

```python
    verdicts = collections.Counter(r["rebrand_verdict"] for r in rows if r["rebrand_verdict"])
    if verdicts:
        print("Rebrand verdicts (C-candidate):")
        for v, n in verdicts.most_common():
            print(f"  {v}: {n}")
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `uv run --with pytest --with requests --with beautifulsoup4 --with pyyaml --with openpyxl pytest utils/tests/test_link_review.py -v`
Expected: 16 PASS (including the pre-existing `test_confidence_and_action`, which exercises the 3-arg call).

- [ ] **Step 5: Regenerate the master sheet and verify counts**

Run: `uv run utils/link_checker.py classify`
Expected output includes (order may vary):

```
Rebrand verdicts (C-candidate):
  probably-fine: 293
  probably-broken: 147
  needs-human: 60
```

and the same category counts as before (live 3444, A 1218, blocked-unknown 655, C-candidate 500, B? 54, needs-human 42). If verdict counts differ from 147/293/60, stop and investigate before committing — the helpers diverge from the validated prototype.

- [ ] **Step 6: Spot-check rows**

Run:

```bash
uv run python -c "
import csv
rows = [r for r in csv.DictReader(open('utils/link_review_master.csv')) if r['rebrand_verdict']]
for v in ('probably-broken', 'probably-fine', 'needs-human'):
    print('==', v)
    for r in [x for x in rows if x['rebrand_verdict'] == v][:15]:
        print('  ', r['final_url'][:60], '|', r['history_signal'][:40], '|', r['suggested_action'])
"
```

Expected: probably-broken rows show homepage-shaped final URLs with `salvage-wayback`/`remove-or-replace`; probably-fine rows show deep links with non-empty `history_signal` and `update-to-final-url`; needs-human rows show `needs-subjective-review`.

- [ ] **Step 7: Commit (code + regenerated data)**

```bash
git add utils/link_checker.py utils/tests/test_link_review.py utils/link_review_master.csv utils/link_review_master.xlsx
git commit -m "feat: add rebrand verdict columns to master sheet (147/293/60 split)"
```

---

### Task 3: Page aggregation helpers and generic xlsx writer

Pure functions + a small DRY refactor of the xlsx writer. No CLI wiring yet.

**Files:**
- Modify: `utils/link_checker.py` — replace `write_master_xlsx` (line ~806) with a generic writer + wrapper; add page-aggregation helpers after it
- Test: `utils/tests/test_link_review.py`

**Interfaces:**
- Consumes: master-sheet row dicts as loaded by `_load_csv` (all values are **strings**, e.g. `bulk_delete_candidate` is `"True"`/`"False"`) or produced in-process; only these keys are read: `section`, `page_title`, `page_url`, `source_file`, `broken_category`, `rebrand_verdict`, `wayback_status`, `bulk_delete_candidate`.
- Produces (Task 4 depends on these):
  - `write_review_xlsx(rows: list[dict], path: Path, fieldnames: list[str], sheet_title: str, widths: dict[str, int]) -> None`
  - `write_master_xlsx(rows, path)` — kept as a thin wrapper so the existing test and `run_classify` are untouched
  - `subsection_of(source_file: str) -> str`
  - `suggested_page_action(subsection: str, broken: int, broken_no_wayback: int) -> str`
  - `aggregate_pages(rows: list[dict]) -> list[dict]` — one dict per page with ≥1 non-live link, keys = `PAGES_FIELDNAMES`, sorted by `source_file`
  - Constants `PAGES_FIELDNAMES: list[str]`, `LINK_CENTRIC_SUBSECTIONS: set[str]`

- [ ] **Step 1: Write the failing tests**

Append to `utils/tests/test_link_review.py`:

```python
def _mk_link(source_file="history-content/website-reviews/foo-123.md",
             section="history-content", category="live", verdict="",
             wayback="", bulk=False):
    return {
        "section": section, "page_title": "Foo", "page_url": "/x/123",
        "source_file": source_file, "broken_category": category,
        "rebrand_verdict": verdict, "wayback_status": wayback,
        "bulk_delete_candidate": str(bulk),
    }


def test_subsection_of():
    assert lc.subsection_of("history-content/website-reviews/foo-1.md") == "website-reviews"
    assert lc.subsection_of("blog/a-post-2.md") == ""


def test_suggested_page_action():
    # Link-centric page with an un-archived broken link → delete candidate:
    assert lc.suggested_page_action("website-reviews", broken=1, broken_no_wayback=1) == "delete-page-candidate"
    # Link-centric, every broken link archived → salvage:
    assert lc.suggested_page_action("national-resources", broken=2, broken_no_wayback=0) == "salvage-wayback"
    # Link-centric but nothing broken → just fix links:
    assert lc.suggested_page_action("website-reviews", broken=0, broken_no_wayback=0) == "fix-links-only"
    # Content-centric sections never get delete suggestions:
    assert lc.suggested_page_action("teaching-guides", broken=5, broken_no_wayback=5) == "fix-links-only"


def test_aggregate_pages_counts_and_filtering():
    rows = [
        # Page 1: website review — one dead link without wayback, one live:
        _mk_link(category="A", wayback="not_archived"),
        _mk_link(category="live"),
        # Page 2: all live → excluded from the sheet:
        _mk_link(source_file="blog/fine-1.md", section="blog", category="live"),
        # Page 3: teaching guide — probably-broken rebrand that HAS a snapshot:
        _mk_link(source_file="teaching-materials/teaching-guides/g-9.md",
                 section="teaching-materials", category="C-candidate",
                 verdict="probably-broken", wayback="found", bulk=True),
    ]
    pages = {p["source_file"]: p for p in lc.aggregate_pages(rows)}

    assert "blog/fine-1.md" not in pages  # all-live pages excluded

    review = pages["history-content/website-reviews/foo-123.md"]
    assert review["subsection"] == "website-reviews"
    assert review["total_links"] == 2
    assert review["live"] == 1
    assert review["dead_A"] == 1
    assert review["broken_no_wayback"] == 1
    assert review["suggested_page_action"] == "delete-page-candidate"

    guide = pages["teaching-materials/teaching-guides/g-9.md"]
    assert guide["rebrand_probably_broken"] == 1
    assert guide["broken_with_wayback"] == 1
    assert guide["bulk_delete_candidates"] == 1
    assert guide["suggested_page_action"] == "fix-links-only"


def test_write_review_xlsx_generic(tmp_path):
    import openpyxl
    fieldnames = ["a", "b"]
    out = tmp_path / "pages.xlsx"
    lc.write_review_xlsx([{"a": 1, "b": "x"}], out, fieldnames, "page_review", {"a": 20})
    wb = openpyxl.load_workbook(out)
    ws = wb.active
    assert ws.title == "page_review"
    assert [c.value for c in ws[1]] == fieldnames
    assert ws.freeze_panes == "A2"
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `uv run --with pytest --with requests --with beautifulsoup4 --with pyyaml --with openpyxl pytest utils/tests/test_link_review.py -v`
Expected: 4 new tests FAIL with `AttributeError` (no `subsection_of` / `suggested_page_action` / `aggregate_pages` / `write_review_xlsx`); 16 existing PASS.

- [ ] **Step 3: Implement — generic xlsx writer first**

Replace the entire `write_master_xlsx` function with:

```python
def write_review_xlsx(rows: list[dict], path: Path, fieldnames: list[str],
                      sheet_title: str, widths: dict[str, int]) -> None:
    """Write a review sheet as .xlsx with a frozen header and autofilter."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.append(fieldnames)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([row.get(col, "") for col in fieldnames])

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{ws.cell(row=1, column=len(fieldnames)).column_letter}{ws.max_row}"
    for i, col in enumerate(fieldnames, 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = widths.get(col, 16)
    wb.save(path)


MASTER_XLSX_WIDTHS = {"page_title": 40, "source_file": 40, "link_url": 50,
                      "link_text": 30, "final_url": 40, "remote_title": 30,
                      "history_signal": 30}


def write_master_xlsx(rows: list[dict], path: Path) -> None:
    write_review_xlsx(rows, path, MASTER_FIELDNAMES, "link_review", MASTER_XLSX_WIDTHS)
```

(The existing `test_write_master_xlsx` keeps passing — same signature, same output shape.)

- [ ] **Step 4: Implement — page aggregation**

Insert after `write_master_xlsx`:

```python
LINK_CENTRIC_SUBSECTIONS = {"website-reviews", "national-resources"}

PAGES_FIELDNAMES = [
    "section", "subsection", "page_title", "page_url", "source_file",
    "total_links", "live", "dead_A",
    "rebrand_probably_broken", "rebrand_probably_fine", "rebrand_needs_human",
    "soft404_B", "blocked_unknown", "needs_human", "bulk_delete_candidates",
    "broken_with_wayback", "broken_no_wayback",
    "suggested_page_action",
]


def subsection_of(source_file: str) -> str:
    """Second path segment (section/subsection/file.md), or '' when flat."""
    parts = Path(source_file).parts
    return parts[1] if len(parts) > 2 else ""


def suggested_page_action(subsection: str, broken: int, broken_no_wayback: int) -> str:
    """Advisory page-level verdict. 'Broken' = dead_A + rebrand_probably_broken."""
    if subsection in LINK_CENTRIC_SUBSECTIONS:
        if broken_no_wayback >= 1:
            return "delete-page-candidate"
        if broken >= 1:
            return "salvage-wayback"
    return "fix-links-only"


def aggregate_pages(rows: list[dict]) -> list[dict]:
    """One row per page with >=1 non-live link. Accepts CSV rows (str values)."""
    by_page: dict[str, list[dict]] = {}
    for r in rows:
        by_page.setdefault(r["source_file"], []).append(r)

    out = []
    for source_file, links in sorted(by_page.items()):
        cats = collections.Counter(r["broken_category"] for r in links)
        if cats.get("live", 0) == len(links):
            continue
        verdicts = collections.Counter(
            r.get("rebrand_verdict", "") for r in links if r.get("rebrand_verdict"))
        broken = [r for r in links
                  if r["broken_category"] == "A"
                  or r.get("rebrand_verdict") == "probably-broken"]
        with_wayback = sum(1 for r in broken if r.get("wayback_status") == "found")
        subsection = subsection_of(source_file)
        first = links[0]
        out.append({
            "section": first["section"],
            "subsection": subsection,
            "page_title": first["page_title"],
            "page_url": first["page_url"],
            "source_file": source_file,
            "total_links": len(links),
            "live": cats.get("live", 0),
            "dead_A": cats.get("A", 0),
            "rebrand_probably_broken": verdicts.get("probably-broken", 0),
            "rebrand_probably_fine": verdicts.get("probably-fine", 0),
            "rebrand_needs_human": verdicts.get("needs-human", 0),
            "soft404_B": cats.get("B?", 0),
            "blocked_unknown": cats.get("blocked-unknown", 0),
            "needs_human": cats.get("needs-human", 0),
            "bulk_delete_candidates": sum(
                1 for r in links if str(r.get("bulk_delete_candidate")) == "True"),
            "broken_with_wayback": with_wayback,
            "broken_no_wayback": len(broken) - with_wayback,
            "suggested_page_action": suggested_page_action(
                subsection, len(broken), len(broken) - with_wayback),
        })
    return out
```

- [ ] **Step 5: Run tests to verify all pass**

Run: `uv run --with pytest --with requests --with beautifulsoup4 --with pyyaml --with openpyxl pytest utils/tests/test_link_review.py -v`
Expected: 20 PASS (including the untouched `test_write_master_xlsx`).

- [ ] **Step 6: Commit**

```bash
git add utils/link_checker.py utils/tests/test_link_review.py
git commit -m "feat: add page aggregation helpers and generic review-sheet xlsx writer"
```

---

### Task 4: `pages` subcommand, real-data run, and docs

**Files:**
- Modify: `utils/link_checker.py` — path constants (near `MASTER_CSV`, line ~723), new `run_pages()` (after `run_classify`), CLI in `main()` (line ~913), module docstring usage block (line ~13)
- Modify: `docs/todo.md`, `CLAUDE.md` (repo root, "External Link Checker" section), `docs/superpowers/specs/2026-07-20-rebrand-triage-and-page-sheet-design.md` (status/handoff)
- Create (generated): `utils/link_review_pages.csv`, `utils/link_review_pages.xlsx`

**Interfaces:**
- Consumes (from Tasks 2–3): master CSV with `rebrand_verdict` column; `aggregate_pages(rows)`; `write_review_xlsx(...)`; `_load_csv(path)`.
- Produces: `uv run utils/link_checker.py pages` → `utils/link_review_pages.csv` + `.xlsx`.

- [ ] **Step 1: Add path constants**

Next to `MASTER_CSV` / `MASTER_XLSX` (line ~723):

```python
PAGES_CSV = OUTPUT_DIR / "link_review_pages.csv"
PAGES_XLSX = OUTPUT_DIR / "link_review_pages.xlsx"
PAGES_XLSX_WIDTHS = {"page_title": 40, "source_file": 50, "page_url": 30}
```

- [ ] **Step 2: Implement `run_pages`**

Insert after `run_classify`:

```python
def run_pages():
    """Aggregate the master sheet into one row per page with problem links."""
    rows = _load_csv(MASTER_CSV)
    if not rows:
        print(f"No master sheet at {MASTER_CSV}. Run 'classify' first.")
        sys.exit(1)
    if "rebrand_verdict" not in rows[0]:
        print(f"{MASTER_CSV} predates the rebrand-verdict columns. Re-run 'classify' first.")
        sys.exit(1)

    pages = aggregate_pages(rows)

    with open(PAGES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PAGES_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(pages)
    print(f"Wrote {PAGES_CSV} ({len(pages)} pages with problem links).")

    write_review_xlsx(pages, PAGES_XLSX, PAGES_FIELDNAMES, "page_review", PAGES_XLSX_WIDTHS)
    print(f"Wrote {PAGES_XLSX}")

    actions = collections.Counter(p["suggested_page_action"] for p in pages)
    for action, n in actions.most_common():
        print(f"  {action}: {n}")
```

- [ ] **Step 3: Wire the CLI and docstring**

In `main()`, after the `classify` parser line:

```python
    sub.add_parser("pages", help="Aggregate master sheet into one row per page (run classify first)")
```

In the dispatch chain, after the `classify` branch:

```python
    elif args.command == "pages":
        run_pages()
```

In the module docstring usage block, after the `classify` line:

```
    uv run utils/link_checker.py pages                # Aggregate master sheet into per-page review sheet
```

- [ ] **Step 4: Run the full test suite (regression gate)**

Run: `uv run --with pytest --with requests --with beautifulsoup4 --with pyyaml --with openpyxl pytest utils/tests/test_link_review.py -v`
Expected: 20 PASS.

- [ ] **Step 5: Run on real data and verify**

Run: `uv run utils/link_checker.py pages`
Expected: `Wrote .../link_review_pages.csv (1206 pages with problem links).`, then the xlsx line, then action counts (values not pre-known — record them).

Guard-rail check that `pages` errors correctly: `mv utils/link_review_master.csv utils/link_review_master.csv.bak && uv run utils/link_checker.py pages; mv utils/link_review_master.csv.bak utils/link_review_master.csv`
Expected: `No master sheet at ... Run 'classify' first.` and exit code 1.

Spot-check delete candidates:

```bash
uv run python -c "
import csv
rows = list(csv.DictReader(open('utils/link_review_pages.csv')))
dels = [r for r in rows if r['suggested_page_action'] == 'delete-page-candidate']
print(len(dels), 'delete-page-candidates')
for r in dels[:8]:
    print('  ', r['subsection'], r['source_file'][:60], 'broken_no_wayback=', r['broken_no_wayback'])
"
```

Expected: every printed row has `subsection` in {website-reviews, national-resources} and `broken_no_wayback >= 1`. Open `utils/link_review_pages.xlsx` and confirm frozen header + autofilter.

- [ ] **Step 6: Update docs**

1. `docs/todo.md` → "Link Review & Cleanup": note the rebrand verdict split (500 C-candidates → 147 probably-broken / 293 probably-fine / 60 needs-human, sheet columns `rebrand_verdict` etc.) and the new `pages` sheet for bulk page decisions; update the team-review bullet to start from `link_review_pages.xlsx` for delete calls and the master sheet for link-level calls; bump the "Last updated" date to 2026-07-20.
2. Root `CLAUDE.md` → "External Link Checker" command list: add `uv run utils/link_checker.py pages` with a one-line description, and mention `link_review_pages.csv` in the outputs sentence.
3. `docs/superpowers/specs/2026-07-20-rebrand-triage-and-page-sheet-design.md` → change **Status** to "Implemented" and append a short "Status & handoff" note: implemented on `fix/dead-links`, real-data counts observed, apply step still deferred.

- [ ] **Step 7: Commit (code + generated sheets + docs)**

```bash
git add utils/link_checker.py utils/link_review_pages.csv utils/link_review_pages.xlsx docs/todo.md CLAUDE.md docs/superpowers/specs/2026-07-20-rebrand-triage-and-page-sheet-design.md
git commit -m "feat: add pages subcommand producing per-page review sheet"
```
