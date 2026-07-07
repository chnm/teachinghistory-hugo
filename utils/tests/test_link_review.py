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
