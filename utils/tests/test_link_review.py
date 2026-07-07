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
