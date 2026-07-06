# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests",
#     "beautifulsoup4",
#     "pyyaml",
# ]
# ///
"""
Deterministic legacy -> native URL redirect pipeline for Drupal/Omeka/WordPress ->
Hugo migrations. Generates a Caddy redirect snippet and verifies it over HTTP.

The authoritative record of what Hugo serves is the build artifact `public/redirects.json`
(emitted by layouts/index.redirects.json). The /node/{id} legacy form and the Drupal taxonomy
facets are sourced from committed dumps of Drupal's path_alias table (utils/node_redirects.tsv,
utils/taxonomy_aliases.tsv) and joined against that manifest — so node ids and term slugs don't
have to live in content front matter. See docs/REDIRECTS.md.

Subcommands:
    build       Hugo manifest + node_redirects.tsv (path_alias dump) -> base legacy->native
                map (utils/redirect_map.csv). /node/{id} is the UNION of front-matter
                drupal_nid and the dump (the dump adds nodes with no front-matter nid).
    taxonomy    Join utils/taxonomy_aliases.tsv (Drupal /category/{vocab}/{slug} dump) to the
                Hugo manifest -> utils/taxonomy_redirects.csv (exact term page, else a verified
                vocabulary-level landing). Merged by `reconcile`.
    reconcile   Merge externally-discovered old URLs (utils/old_urls.csv) + taxonomy_redirects.csv,
                and apply the parent-section fallback to anything unmatched. Rewrites redirect_map.csv.
    generate    Emit teachinghistory-website/static/redirects.caddy (a `map` block, 301s); Hugo copies it to public/.
    verify      HTTP-check every mapping against a running target (Caddy+Hugo).
    crosscheck  Oracle: for each dump nid, confirm the LIVE old site's /node/{nid} 301s to the
                alias we recorded (no sitemap needed). QA only; does not change the map.
    crawl       CMS-agnostic seam: enumerate old URLs from the old site's sitemap.xml.

Usage:
    uv run utils/redirect_mapper.py build       [--manifest https://dev.teachinghistory.org/redirects.json]
    uv run utils/redirect_mapper.py taxonomy    [--manifest https://dev.teachinghistory.org/redirects.json]
    uv run utils/redirect_mapper.py reconcile
    uv run utils/redirect_mapper.py generate
    uv run utils/redirect_mapper.py verify --target https://dev.teachinghistory.org
    uv run utils/redirect_mapper.py crosscheck --old-site https://teachinghistory.org --limit 200
    uv run utils/redirect_mapper.py crawl --old-site https://example.org

Pluggable seams for other CMSes:
    * map source        -> load_manifest() (any Hugo site emits the same manifest shape)
    * identity source   -> load_node_aliases() (Drupal path_alias dump; swap per CMS)
    * URL enumerator    -> run_crawl() (sitemap parsing is generic; add per-CMS fallbacks)
"""

import argparse
import concurrent.futures as cf
import csv
import json
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_DIR = REPO_ROOT / "teachinghistory-website"
OUTPUT_DIR = REPO_ROOT / "utils"

MANIFEST_DEFAULT = WEBSITE_DIR / "public" / "redirects.json"
MAP_CSV = OUTPUT_DIR / "redirect_map.csv"
OLD_URLS_CSV = OUTPUT_DIR / "old_urls.csv"
NODE_REDIRECTS_TSV = OUTPUT_DIR / "node_redirects.tsv"       # Drupal path_alias dump: nid -> pretty alias (source of /node/{id})
TAXONOMY_ALIASES_TSV = OUTPUT_DIR / "taxonomy_aliases.tsv"   # Drupal path_alias dump: taxonomy facet aliases (input to `taxonomy`)
TAXONOMY_TERM_OVERRIDES = OUTPUT_DIR / "taxonomy_term_overrides.csv"  # curated: aliasless /taxonomy/term/{id} -> Hugo term (resolved by Drupal title)
TAXONOMY_CSV = OUTPUT_DIR / "taxonomy_redirects.csv"         # GENERATED Drupal facet alias -> Hugo term/section URL (merged by reconcile)
CURATED_CSV = OUTPUT_DIR / "curated_redirects.csv"          # curated old -> new for renamed/moved pages the dumps can't cover (merged by reconcile)
CROSSCHECK_CSV = OUTPUT_DIR / "redirect_crosscheck.csv"
VERIFY_CSV = OUTPUT_DIR / "redirect_verify.csv"
PARITY_CSV = OUTPUT_DIR / "redirect_parity.csv"
CADDY_OUT = WEBSITE_DIR / "static" / "redirects.caddy"  # Hugo copies static/ -> public/, so this ships in the release artifact

MAP_FIELDS = ["old_url", "native_url", "match_via", "nid", "source_file", "status", "notes"]

REQUEST_TIMEOUT = 15
REQUEST_DELAY = 0.3  # seconds between requests
USER_AGENT = "TeachingHistory-RedirectMapper/1.0 (site migration)"


# --- Shared helpers ---------------------------------------------------------

def load_manifest(source: str | Path) -> dict:
    """Load the Hugo redirect manifest from a local file path or an http(s) URL."""
    s = str(source)
    if s.startswith(("http://", "https://")):
        resp = requests.get(s, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        return resp.json()
    p = Path(source)
    if not p.exists():
        print(f"Manifest not found: {p}\nRun `hugo` (e.g. `just build`) first to emit public/redirects.json.")
        sys.exit(1)
    return json.loads(p.read_text(encoding="utf-8"))


def path_only(u: str) -> str:
    """Reduce a URL or path to a clean absolute path (drop scheme/host/query/fragment)."""
    parsed = urlparse(u)
    p = parsed.path if (parsed.scheme or parsed.netloc) else u
    p = p.split("?", 1)[0].split("#", 1)[0]
    if not p.startswith("/"):
        p = "/" + p
    return p


def slash_variants(p: str) -> list[str]:
    """Both trailing-slash forms of a path (root stays as-is)."""
    if p == "/":
        return ["/"]
    return [p, p[:-1]] if p.endswith("/") else [p, p + "/"]


def norm(p: str) -> str:
    """Normalization key: path without a trailing slash (root -> '/')."""
    p = path_only(p)
    return p if p == "/" else p.rstrip("/")


def is_node_path(p: str) -> bool:
    return path_only(p).startswith("/node/")


def read_map_rows() -> list[dict]:
    if not MAP_CSV.exists():
        print(f"No map found at {MAP_CSV}. Run `build` first.")
        sys.exit(1)
    with open(MAP_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_map_rows(rows: list[dict]):
    rows = sorted(rows, key=lambda r: (r["old_url"], r["native_url"]))
    with open(MAP_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MAP_FIELDS)
        w.writeheader()
        w.writerows(rows)


# --- build ------------------------------------------------------------------

def load_node_aliases() -> list[tuple[int, str]]:
    """Load (nid, drupal_alias) pairs from the committed path_alias dump
    (utils/node_redirects.tsv). Comment/header lines (non-digit col 1) are skipped."""
    if not NODE_REDIRECTS_TSV.exists():
        return []
    out = []
    with open(NODE_REDIRECTS_TSV, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 2 or not parts[0].strip().isdigit():
                continue
            out.append((int(parts[0].strip()), path_only(parts[1].strip())))
    return out


def served_index(manifest: dict) -> dict[str, str]:
    """norm(path) -> current native URL, for every native path AND every `aliases:`
    path Hugo serves. Lets a Drupal pretty alias (from the path_alias dump) resolve to
    the page's current native URL — even for a retired node whose alias was moved onto a
    surviving page (the alias -> survivor's native)."""
    served: dict[str, str] = {}
    for pg in manifest.get("pages", []):
        native = pg["native"]
        served[norm(native)] = native
        for legacy in pg.get("legacy_paths", []):
            if is_node_path(legacy):
                continue  # /node/{id} is synthetic, not a served slug
            served.setdefault(norm(legacy), native)
    return served


def run_build(manifest_src):
    manifest = load_manifest(manifest_src)
    pages = manifest.get("pages", [])
    served = served_index(manifest)
    src_by_native = {norm(pg["native"]): pg.get("source_file", "") for pg in pages}
    rows = []
    seen_old: set[str] = set()

    def add(old, native, via, nid, src, note=""):
        key = path_only(old)
        if key in seen_old:
            return False
        seen_old.add(key)
        rows.append({
            "old_url": key, "native_url": native, "match_via": via,
            "nid": "" if nid in (None, "") else str(nid),
            "source_file": src, "status": "matched", "notes": note,
        })
        return True

    # 1. Manifest legacy_paths: `aliases:` (pretty Drupal paths) + the synthesized
    #    /node/{drupal_nid} path. This keeps every front-matter node covered — including
    #    the handful whose nid has no row in the path_alias dump (Drupal served them only
    #    at /node/{id}, no pretty alias).
    for pg in pages:
        native, nid, src = pg["native"], pg.get("nid"), pg.get("source_file", "")
        for legacy in pg.get("legacy_paths", []):
            if is_node_path(legacy):
                add(legacy, native, "node", nid, src)
            else:
                add(legacy, native, "alias", "", src)

    # 2. /node/{id} from the path_alias dump (utils/node_redirects.tsv) — the authoritative
    #    source. Joined to the page's current native via served_index, so it tracks URL
    #    moves. UNION with step 1: adds nodes whose /node/{id} isn't derivable from front
    #    matter (e.g. retired Beyond-the-Textbook parts whose alias lives on the survivor).
    #    A dump slug Hugo doesn't serve (unpublished/removed node) is skipped, not 404'd.
    node_added = node_skipped = 0
    for nid, slug in load_node_aliases():
        native = served.get(norm(slug))
        if native is None:
            node_skipped += 1
            continue
        if add(f"/node/{nid}", native, "node", nid, src_by_native.get(norm(native), ""), "path_alias"):
            node_added += 1

    write_map_rows(rows)
    aliases = sum(1 for r in rows if r["match_via"] == "alias")
    nodes = sum(1 for r in rows if r["match_via"] == "node")
    print(f"Built {len(rows)} legacy->native pairs from {len(pages)} pages.")
    print(f"  alias paths:                       {aliases}")
    print(f"  node paths (front matter + dump):  {nodes}")
    print(f"  node paths added by path_alias dump ({NODE_REDIRECTS_TSV.name}): {node_added}"
          + (f"  ({node_skipped} dump slugs skipped — not served on Hugo: unpublished/removed)" if node_skipped else ""))
    print(f"Wrote {MAP_CSV}")


# --- reconcile (parent-section fallback) ------------------------------------

def learn_prefix_remap(rows: list[dict]) -> dict[str, str]:
    """From matched alias rows, learn old-first-segment -> new-first-segment
    (e.g. /nhec-blog -> /blog). Deterministic: most common wins, ties by sort."""
    votes: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        if r["status"] != "matched" or r["match_via"] != "alias":
            continue
        old_seg = path_only(r["old_url"]).strip("/").split("/", 1)[0]
        new_seg = path_only(r["native_url"]).strip("/").split("/", 1)[0]
        if old_seg and new_seg:
            votes[old_seg][new_seg] += 1
    remap = {}
    for old_seg, counter in votes.items():
        best = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        if best != old_seg:
            remap[old_seg] = best
    return remap


def parent_fallback(old_url: str, valid_targets: set[str], remap: dict[str, str]) -> tuple[str, str]:
    """Pick the nearest existing ancestor page for an unmatched old URL.
    Returns (target, note). Falls back to '/' which always exists."""
    p = path_only(old_url)
    segs = p.strip("/").split("/")
    note = ""
    if segs and segs[0] in remap:
        note = f"prefix {segs[0]}->{remap[segs[0]]}"
        segs[0] = remap[segs[0]]
    # Try progressively shorter ancestors: /a/b/ , /a/ , /
    for i in range(len(segs) - 1, 0, -1):
        cand = "/" + "/".join(segs[:i]) + "/"
        if cand in valid_targets:
            return cand, (note + "; " if note else "") + f"ancestor {cand}"
    return "/", (note + "; " if note else "") + "root fallback"


def run_reconcile(manifest_src):
    rows = read_map_rows()
    manifest = load_manifest(manifest_src)
    valid_targets = set(manifest.get("valid_targets", []))
    served = served_index(manifest)
    nid_index = {}
    path_index = {}
    for pg in manifest.get("pages", []):
        native = pg["native"]
        if pg.get("nid") is not None:
            nid_index[str(pg["nid"])] = native
        for legacy in pg.get("legacy_paths", []):
            if not is_node_path(legacy):
                path_index[norm(legacy)] = native
    # Also index nids from the path_alias dump (covers nodes absent from front matter).
    for nid, slug in load_node_aliases():
        native = served.get(norm(slug))
        if native is not None:
            nid_index.setdefault(str(nid), native)

    known = {norm(r["old_url"]) for r in rows}
    remap = learn_prefix_remap(rows)

    old_urls = []
    if OLD_URLS_CSV.exists():
        with open(OLD_URLS_CSV, encoding="utf-8") as f:
            old_urls = [row["old_url"] for row in csv.DictReader(f) if row.get("old_url")]

    added = matched = fallback = 0
    for ou in old_urls:
        key = norm(ou)
        if key in known:
            continue
        known.add(key)
        added += 1
        # direct path hit
        if key in path_index:
            target, via, status, note = path_index[key], "path", "matched", ""
            matched += 1
        # /node/{nid}
        elif path_only(ou).startswith("/node/") and path_only(ou).split("/")[2].isdigit() \
                and path_only(ou).split("/")[2] in nid_index:
            n = path_only(ou).split("/")[2]
            target, via, status, note = nid_index[n], "node", "matched", ""
            matched += 1
        else:
            target, note = parent_fallback(ou, valid_targets, remap)
            via, status = "parent_fallback", "parent_fallback"
            fallback += 1
        rows.append({
            "old_url": path_only(ou), "native_url": target, "match_via": via,
            "nid": "", "source_file": "", "status": status, "notes": note,
        })

    # --- Curated redirects (renamed/moved pages the dumps can't cover) --------------
    # Hand-authored old->new for pages that were renamed or folded post-migration (e.g.
    # /nhec-blog -> /blog/, /quick-links-elementary -> the elementary quick-links page).
    # These have no path_alias/node/taxonomy row, so they'd 404 or hit a weak parent
    # fallback. Every target is HTTP-verified 200 before being added here.
    cur_added = cur_skipped = 0
    if CURATED_CSV.exists():
        with open(CURATED_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                old = (row.get("old_url") or "").strip()
                native = (row.get("native_url") or "").strip()
                if not old or not native:
                    continue
                key = norm(old)
                if key in known:  # already covered by a manifest alias/native; don't override
                    cur_skipped += 1
                    continue
                known.add(key)
                rows.append({
                    "old_url": path_only(old), "native_url": native, "match_via": "curated",
                    "nid": "", "source_file": "", "status": "matched",
                    "notes": (row.get("note") or "curated").strip(),
                })
                cur_added += 1

    # --- Taxonomy facet redirects (generated by the `taxonomy` subcommand) ---------
    # Drupal browsed content at /category/{vocab}/{slug}; Hugo emits its taxonomies at
    # /tags|/topics|/time_periods|/evidence_types/{slug}/ with differing term slugs, and
    # many Drupal vocabularies have no Hugo taxonomy at all. Those pairs can't flow through
    # the manifest, so utils/taxonomy_redirects.csv (produced by `taxonomy`, every target
    # HTTP-200 in the manifest) is merged here as pre-resolved matched rows.
    tax_added = tax_skipped = 0
    if TAXONOMY_CSV.exists():
        with open(TAXONOMY_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                old = (row.get("old_url") or "").strip()
                native = (row.get("native_url") or "").strip()
                if not old or not native:
                    continue
                key = norm(old)
                if key in known:  # a manifest alias already covers it; don't double-map
                    tax_skipped += 1
                    continue
                known.add(key)
                rows.append({
                    "old_url": path_only(old), "native_url": native, "match_via": "taxonomy",
                    "nid": "", "source_file": "", "status": "matched",
                    "notes": (row.get("notes") or "taxonomy facet").strip(),
                })
                tax_added += 1

    write_map_rows(rows)
    print(f"Reconciled. Learned prefix remaps: {remap or '(none)'}")
    print(f"  external old URLs considered: {len(old_urls)} (new: {added})")
    print(f"  newly matched: {matched} | parent-fallback: {fallback}")
    print(f"  curated redirects: {cur_added}" + (f" ({cur_skipped} already covered)" if cur_skipped else ""))
    print(f"  taxonomy facet redirects: {tax_added}" + (f" ({tax_skipped} already covered)" if tax_skipped else ""))
    print(f"Map now has {len(rows)} rows -> {MAP_CSV}")
    if not old_urls:
        print("Note: no utils/old_urls.csv found (no sitemap on this site) — map = manifest only.")


# --- taxonomy (Drupal facet alias -> Hugo term/section URL) -----------------

# Hugo taxonomies (from hugo.toml [taxonomies]). Term URLs look like /{tax}/{slug}/.
HUGO_TAXONOMIES = ["tags", "topics", "time_periods", "evidence_types", "categories"]

# Drupal vocabulary -> ordered Hugo taxonomies to try for an exact term match.
# (A term may live in more than one; the first hit wins.)
VOCAB_TO_TAXONOMIES = {
    "tags": ["tags", "topics", "time_periods", "evidence_types"],
    "keywords": ["tags", "topics"],
    "topic": ["topics"],
    "time-periods": ["time_periods"],
    "media-format": ["evidence_types", "tags"],
    "history-multimedia-type": ["evidence_types", "tags"],
    "history-in-multimedia-type": ["evidence_types", "tags"],
    "ell-languages": ["tags"],
    "ell-type": ["tags"],
    "us-states-and-territories": ["tags"],
    "section": ["tags"],
    "historical-sites-types": ["tags"],
}


_TAX_STOPWORDS = {"of", "the", "to", "a", "an", "and", "in", "on", "for", "with", "at", "by", "from"}


def _taxkey(slug: str) -> str:
    """Normalize a term slug for matching Drupal pathauto slugs against Hugo's urlize output.
    Collapses to [a-z0-9] (health-disease ~ health--disease, science-tech ~ science--tech.)
    AND drops common stopwords, which Drupal's pathauto stripped but Hugo keeps — so the NCHS
    eras match (e.g. `emergence-modern-us-1890-1930` ~ `emergence-of-modern-us-1890-1930`).
    Dropping stopwords only *adds* matches (both sides transform identically); if a slug is
    all stopwords, keep the raw tokens so it still has a key."""
    toks = [t for t in re.split(r"[^a-z0-9]+", slug.lower()) if t]
    kept = [t for t in toks if t not in _TAX_STOPWORDS]
    return "".join(kept or toks)


def _vocab_fallback(vocab: str, leaf: str, segs: list[str], valid: set[str]) -> tuple[str, str]:
    """Best verified landing page for a Drupal facet whose term has no Hugo term page.
    Returns (target, reason); target is always present in `valid` (or '/')."""
    def ok(u):
        return u if u in valid else None

    if vocab in ("tags", "keywords", "us-states-and-territories", "historical-sites-types"):
        return ok("/tags/") or "/", "index tags"
    if vocab == "topic":
        return ok("/topics/") or "/", "index topics"
    if vocab == "time-periods":
        return ok("/time_periods/") or "/", "index time_periods"
    if vocab in ("media-format", "history-multimedia-type", "history-in-multimedia-type"):
        return ok("/evidence_types/") or "/", "index evidence_types"
    if vocab in ("ell-languages", "ell-type"):
        return ok("/teaching-materials/english-language-learners/") or "/", "section ELL"
    if vocab == "vetted-lesson-plan-characteristics":
        return ok("/teaching-materials/lesson-plan-reviews/") or "/", "section lesson-plan-reviews"
    if vocab == "grade-level":
        elem = {"pre-k", "prekindergarten", "k", "kindergarten", "1", "first-grade", "2",
                "second-grade", "3", "third-grade", "4", "fourth-grade", "5", "fifth-grade"}
        mid = {"6", "sixth-grade", "7", "seventh-grade", "8", "eighth-grade"}
        high = {"9", "ninth-grade", "10", "tenth-grade", "11", "eleventh-grade", "12", "twelfth-grade"}
        band = ("/elementary-quick-links/" if leaf in elem else
                "/middle-quick-links/" if leaf in mid else
                "/high-quick-links/" if leaf in high else None)
        return (ok(band) or "/", f"grade-band {leaf}") if band else ("/", "grade-band unknown")
    if vocab == "quicklinks":
        blob = "/".join(segs[2:])
        band = ("/elementary-quick-links/" if re.search(r"element|k-2|3-5", blob) else
                "/middle-quick-links/" if re.search(r"middle|6-8", blob) else
                "/high-quick-links/" if re.search(r"high|9-12", blob) else
                "/teaching-materials/")
        return ok(band) or "/", "quick-links"
    if vocab == "section":
        sect = {
            "history-content": "/history-content/", "best-practices": "/best-practices/",
            "digital-classroom": "/digital-classroom/", "teaching-materials": "/teaching-materials/",
            "about": "/about/", "nhec-blog": "/blog/", "blog": "/blog/",
        }.get(segs[2] if len(segs) > 2 else "", None)
        return (ok(sect) or "/", f"section {segs[2]}") if sect else ("/", "section other")
    return "/", "root"


def run_taxonomy(manifest_src):
    """Generate utils/taxonomy_redirects.csv from the committed Drupal taxonomy alias dump
    (utils/taxonomy_aliases.tsv) joined to the Hugo manifest. Every /category/{vocab}/{slug}
    facet maps to the exact Hugo term page when that term still exists, else to a verified
    vocabulary-level index/section landing page. The canonical /taxonomy/term/{id} form is
    also emitted (aliased term-ids from the dump; aliasless high-traffic ones from
    utils/taxonomy_term_overrides.csv). /feed variants are intentionally not emitted."""
    if not TAXONOMY_ALIASES_TSV.exists():
        print(f"No {TAXONOMY_ALIASES_TSV} — nothing to do.")
        return
    manifest = load_manifest(manifest_src)
    valid = set(manifest.get("valid_targets", []))
    # normkey(slug) -> term URL, per Hugo taxonomy
    tax_index: dict[str, dict[str, str]] = {t: {} for t in HUGO_TAXONOMIES}
    for t in valid:
        mm = re.match(r"^/([a-z_]+)/(.+)/$", t)
        if mm and mm.group(1) in tax_index:
            tax_index[mm.group(1)].setdefault(_taxkey(mm.group(2)), t)

    # Load + dedupe aliases (drop the /feed suffix to a base; remember which had a feed and the
    # raw /taxonomy/term/{id} source, so we can also redirect the raw term URL — Drupal served
    # both the pretty /category/… alias AND the canonical /taxonomy/term/{id}, and the latter is
    # itself top traffic).
    bases: dict[str, None] = {}
    termid_of: dict[str, str] = {}  # base alias -> /taxonomy/term/{id}
    with open(TAXONOMY_ALIASES_TSV, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 2 or not parts[0].startswith("/"):
                continue
            alias = path_only(parts[0].strip())
            source = parts[1].strip()
            if alias.endswith("/feed"):
                bases.setdefault(alias[: -len("/feed")], None)  # register base; feeds not emitted
            else:
                bases.setdefault(alias, None)
                m = re.match(r"^/taxonomy/term/(\d+)", source)
                if m:
                    termid_of[alias] = f"/taxonomy/term/{m.group(1)}"

    def resolve(alias: str) -> tuple[str, str]:
        segs = alias.strip("/").split("/")
        vocab = segs[1] if len(segs) >= 3 and segs[0] == "category" else None
        leaf = segs[-1]
        if vocab is not None:
            for tax in VOCAB_TO_TAXONOMIES.get(vocab, ["tags", "topics", "time_periods", "evidence_types"]):
                url = tax_index[tax].get(_taxkey(leaf))
                if url:
                    return url, "exact"
            return _vocab_fallback(vocab, leaf, segs, valid)
        return "/", "root"

    out_rows = []
    stats = Counter()
    termid_target: dict[str, tuple[str, str, bool]] = {}  # term URL -> (target, note, is_exact)
    for base in bases:
        target, reason = resolve(base)
        note = ("taxonomy exact" if reason == "exact" else f"taxonomy fallback ({reason})")
        stats["exact" if reason == "exact" else "fallback"] += 1
        out_rows.append({"old_url": base, "native_url": target, "notes": note})
        tid = termid_of.get(base)
        if tid:
            prev = termid_target.get(tid)
            if prev is None or (reason == "exact" and not prev[2]):  # prefer an exact resolution
                termid_target[tid] = (target, note, reason == "exact")

    # Aliasless term-ids: Drupal served some terms ONLY at /taxonomy/term/{id} (no /category
    # alias, so no dump row) — yet they're heavy traffic (evidence-type / topic / tag browse
    # facets). utils/taxonomy_term_overrides.csv resolves them (Drupal term title -> Hugo term).
    ov_added = 0
    if TAXONOMY_TERM_OVERRIDES.exists():
        with open(TAXONOMY_TERM_OVERRIDES, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                tid = (row.get("term_id") or "").strip()
                native = (row.get("native_url") or "").strip()
                if not tid.isdigit() or not native:
                    continue
                termid_target[f"/taxonomy/term/{tid}"] = (native, f"taxonomy term-override ({row.get('note','')})", True)
                ov_added += 1

    # Raw canonical term URLs: /taxonomy/term/{id} -> the resolved Hugo target. (No /feed
    # variants — old per-term RSS URLs get no measurable traffic and would ~double the map.)
    for tid, (target, note, _) in termid_target.items():
        out_rows.append({"old_url": tid, "native_url": target, "notes": note + ", term-id"})
        stats["term_id"] += 1
    stats["overrides"] = ov_added

    out_rows.sort(key=lambda r: r["old_url"])
    with open(TAXONOMY_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["old_url", "native_url", "notes"])
        w.writeheader()
        w.writerows(out_rows)

    # Sanity: every target must be a served page (or root).
    bad = sorted({r["native_url"] for r in out_rows if r["native_url"] != "/" and r["native_url"] not in valid})
    print(f"Wrote {len(out_rows)} taxonomy redirects -> {TAXONOMY_CSV}")
    print(f"  exact term matches: {stats['exact']} | vocabulary fallbacks: {stats['fallback']} "
          f"| raw /taxonomy/term/ URLs: {stats['term_id']} (of which {stats['overrides']} aliasless overrides)")
    if bad:
        print(f"  WARNING: {len(bad)} targets not in manifest valid_targets: {bad[:10]}")


# --- generate (Caddy) -------------------------------------------------------

def _better(a: dict, b: dict) -> dict:
    """Deterministic conflict winner: matched over fallback, then fewer path
    segments, then lexicographically smaller native."""
    def rank(r):
        seg = path_only(r["native_url"]).strip("/").count("/")
        return (0 if r["status"] == "matched" else 1, seg, r["native_url"])
    return a if rank(a) <= rank(b) else b


def run_generate():
    rows = [r for r in read_map_rows() if r["status"] in ("matched", "parent_fallback")]

    # Resolve to one native per old_url (conflict-safe, deterministic).
    by_old: dict[str, dict] = {}
    conflicts = []
    for r in rows:
        key = path_only(r["old_url"])
        if key in by_old and norm(by_old[key]["native_url"]) != norm(r["native_url"]):
            conflicts.append((key, by_old[key]["native_url"], r["native_url"]))
            by_old[key] = _better(by_old[key], r)
        else:
            by_old.setdefault(key, r)

    # Expand to concrete map keys (both slash variants); drop self-redirect loops.
    mapping: dict[str, str] = {}
    loops = 0
    for old_url, r in by_old.items():
        native = r["native_url"]
        for variant in slash_variants(old_url):
            if variant == native:  # exact self-redirect -> would loop
                loops += 1
                continue
            prev = mapping.get(variant)
            if prev is not None and prev != native:
                # keep deterministic winner
                keep = _better({"native_url": prev, "status": "matched"},
                               {"native_url": native, "status": r["status"]})
                mapping[variant] = keep["native_url"]
            else:
                mapping[variant] = native

    lines = [
        "# redirects.caddy — GENERATED by utils/redirect_mapper.py generate. Do not edit by hand.",
        "# Legacy Drupal path -> native Hugo path (301). Keys sorted; both slash variants emitted.",
        "# Source of truth: teachinghistory-website/public/redirects.json (Hugo manifest).",
        "map {path} {redirect_target} {",
        '\tdefault ""',
    ]
    for key in sorted(mapping):
        lines.append(f"\t{key} {mapping[key]}")
    lines += [
        "}",
        '@hasRedirect expression `{redirect_target} != ""`',
        "redir @hasRedirect {redirect_target} 301",
        "",
    ]
    CADDY_OUT.parent.mkdir(parents=True, exist_ok=True)  # static/ is normally present, but don't assume
    CADDY_OUT.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {len(mapping)} redirect keys ({len(by_old)} unique old URLs) -> {CADDY_OUT}")
    print(f"  skipped self-redirect loop variants: {loops}")
    if conflicts:
        print(f"  CONFLICTS resolved deterministically ({len(conflicts)}): review these:")
        for old_url, a, b in conflicts[:20]:
            print(f"    {old_url}: chose {by_old[old_url]['native_url']}  (candidates: {a} | {b})")


# --- verify -----------------------------------------------------------------

def run_verify(target: str, resume: bool, limit: int | None):
    rows = [r for r in read_map_rows() if r["status"] in ("matched", "parent_fallback")]
    base = target.rstrip("/")

    done = {}
    if resume and VERIFY_CSV.exists():
        with open(VERIFY_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("result"):
                    done[row["old_url"]] = row

    # One test per unique old_url, resolving conflicts the same way generate does
    # (else a conflicting old_url would be checked against the losing native).
    best_by_old: dict[str, dict] = {}
    for r in rows:
        ou = path_only(r["old_url"])
        best_by_old[ou] = r if ou not in best_by_old else _better(best_by_old[ou], r)
    to_check = [(ou, best_by_old[ou]["native_url"]) for ou in sorted(best_by_old) if ou not in done]
    if limit:
        to_check = to_check[:limit]

    session = requests.Session()
    native_cache: dict[str, int | str] = {}
    results = dict(done)
    print(f"Verifying {len(to_check)} redirects against {base} ...")

    for i, (old_url, native) in enumerate(sorted(to_check), 1):
        if i % 100 == 0 or i == 1:
            print(f"  [{i}/{len(to_check)}] {old_url[:70]}")
        got_status = got_loc = ""
        native_status = ""
        result = reason = ""
        try:
            resp = session.get(base + old_url, timeout=REQUEST_TIMEOUT, allow_redirects=False,
                               headers={"User-Agent": USER_AGENT})
            got_status = resp.status_code
            got_loc = resp.headers.get("Location", "")
            loc_path = norm(got_loc) if got_loc else ""
            if got_status not in (301, 308):
                result, reason = "wrong_status", f"expected 301, got {got_status}"
            elif path_only(got_loc) == path_only(old_url):
                # Exact self-redirect only. A /x -> /x/ canonicalization is NOT a loop:
                # /x/ is not a redirect key (the generator drops the equal variant), so
                # it is served directly. norm()-based equality would false-positive here.
                result, reason = "loop", "redirects to itself"
            elif loc_path != norm(native):
                result, reason = "wrong_location", f"-> {got_loc}"
            else:
                # native must serve 200
                if native not in native_cache:
                    nr = session.get(base + native, timeout=REQUEST_TIMEOUT, allow_redirects=True,
                                     headers={"User-Agent": USER_AGENT})
                    native_cache[native] = nr.status_code
                    time.sleep(REQUEST_DELAY)
                native_status = native_cache[native]
                result = "ok" if native_status == 200 else "native_not_200"
                reason = "" if native_status == 200 else f"native returned {native_status}"
        except requests.exceptions.RequestException as e:
            result, reason = "error", str(e)[:150]
        results[old_url] = {
            "old_url": old_url, "expected_native": native, "got_status": got_status,
            "got_location": got_loc, "native_status": native_status,
            "result": result, "reason": reason,
        }
        time.sleep(REQUEST_DELAY)

    fields = ["old_url", "expected_native", "got_status", "got_location",
              "native_status", "result", "reason"]
    with open(VERIFY_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows([results[k] for k in sorted(results)])

    summary = Counter(r["result"] for r in results.values())
    print(f"\nWrote {VERIFY_CSV}")
    for k in sorted(summary):
        print(f"  {k}: {summary[k]}")
    bad = sum(v for k, v in summary.items() if k != "ok")
    if bad:
        print(f"\n{bad} redirects need attention (see non-ok rows in {VERIFY_CSV}).")


# --- crosscheck (live old-site oracle) --------------------------------------

def run_crosscheck(old_site: str, manifest_src, resume: bool, limit: int | None):
    manifest = load_manifest(manifest_src)
    base = old_site.rstrip("/")

    # nid -> (expected alias(es), native). nids come from the path_alias dump
    # (utils/node_redirects.tsv); the native is resolved via the manifest. A dump slug
    # Hugo doesn't serve is skipped (nothing to cross-check).
    served = served_index(manifest)
    aliases_by_native: dict[str, list[str]] = {}
    for pg in manifest.get("pages", []):
        aliases_by_native[pg["native"]] = [path_only(l) for l in pg.get("legacy_paths", []) if not is_node_path(l)]
    targets = []
    for nid, slug in load_node_aliases():
        native = served.get(norm(slug))
        if native is None:
            continue
        aliases = list(aliases_by_native.get(native) or [path_only(native)])
        if path_only(slug) not in aliases:
            aliases.append(path_only(slug))
        targets.append((str(nid), aliases, native))

    done = {}
    fields = ["nid", "node_url", "live_status", "live_location", "expected_alias", "agrees", "reason"]
    if resume and CROSSCHECK_CSV.exists():
        with open(CROSSCHECK_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("agrees"):
                    done[row["nid"]] = row

    todo = [t for t in targets if t[0] not in done]
    if limit:
        todo = todo[:limit]

    session = requests.Session()
    results = dict(done)
    print(f"Cross-checking {len(todo)} node paths against {base} ...")
    for i, (nid, aliases, native) in enumerate(sorted(todo), 1):
        if i % 100 == 0 or i == 1:
            print(f"  [{i}/{len(todo)}] /node/{nid}")
        node_url = f"/node/{nid}"
        live_status = live_loc = agrees = reason = ""
        try:
            resp = session.get(base + node_url, timeout=REQUEST_TIMEOUT, allow_redirects=False,
                               headers={"User-Agent": USER_AGENT})
            live_status = resp.status_code
            live_loc = resp.headers.get("Location", "")
            loc_norm = norm(live_loc) if live_loc else ""
            alias_norms = {norm(a) for a in aliases}
            if live_status in (301, 302, 308) and loc_norm in alias_norms:
                agrees, reason = "yes", ""
            elif live_status == 404:
                agrees, reason = "no", "node 404 on live site (deleted/unpublished)"
            elif live_status in (301, 302, 308):
                agrees, reason = "no", f"live alias {live_loc} != recorded {sorted(alias_norms)}"
            else:
                agrees, reason = "no", f"unexpected status {live_status}"
        except requests.exceptions.RequestException as e:
            agrees, reason = "error", str(e)[:150]
        results[nid] = {
            "nid": nid, "node_url": node_url, "live_status": live_status,
            "live_location": live_loc, "expected_alias": aliases[0] if aliases else "",
            "agrees": agrees, "reason": reason,
        }
        time.sleep(REQUEST_DELAY)

    with open(CROSSCHECK_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows([results[k] for k in sorted(results, key=lambda x: int(x) if x.isdigit() else 0)])

    summary = Counter(r["agrees"] for r in results.values())
    print(f"\nWrote {CROSSCHECK_CSV}")
    for k in sorted(summary):
        print(f"  agrees={k}: {summary[k]}")


# --- crawl (CMS-agnostic seam) ----------------------------------------------

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def _fetch_sitemap_locs(url: str, session: requests.Session, seen: set[str], depth: int = 0) -> list[str]:
    if depth > 3 or url in seen:
        return []
    seen.add(url)
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
    except requests.exceptions.RequestException:
        return []
    if resp.status_code != 200 or "xml" not in resp.headers.get("content-type", "").lower():
        return []
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return []
    locs = []
    if root.tag.endswith("sitemapindex"):
        for sm in root.findall(f"{SITEMAP_NS}sitemap/{SITEMAP_NS}loc"):
            locs += _fetch_sitemap_locs(sm.text.strip(), session, seen, depth + 1)
    else:
        for loc in root.findall(f"{SITEMAP_NS}url/{SITEMAP_NS}loc"):
            locs.append(loc.text.strip())
    return locs


def run_crawl(old_site: str):
    base = old_site.rstrip("/")
    session = requests.Session()
    sitemap_url = urljoin(base + "/", "sitemap.xml")
    print(f"Fetching {sitemap_url} ...")
    locs = _fetch_sitemap_locs(sitemap_url, session, set())
    urls = sorted({path_only(u) for u in locs})
    if not urls:
        print("No sitemap URLs found (this site publishes no XML sitemap). "
              "The map is built from the Hugo manifest instead; nothing to write.")
        return
    with open(OLD_URLS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["old_url"])
        w.writeheader()
        w.writerows([{"old_url": u} for u in urls])
    print(f"Wrote {len(urls)} old URLs -> {OLD_URLS_CSV}")


# Identity extractors (Seam #2). Drupal here needs none (nid is in the manifest);
# provided for CMSes without an embedded identity in the Hugo content.
EXTRACTORS = {
    "drupal": "shortlink|canonical(/node/N)|body.page-node-N",
    "wordpress": "shortlink(?p=N)|body.postid-N|canonical",
    "omeka": "canonical(/items/show/N)|og:url",
}


# --- parity (old-source exists AND new-target exists) -----------------------

_tls = threading.local()


def _session() -> requests.Session:
    s = getattr(_tls, "s", None)
    if s is None:
        s = _tls.s = requests.Session()
    return s


def _final_status(url: str, retries: int = 2) -> tuple:
    """GET following redirects; return (status_code_or_ERR, final_url)."""
    for attempt in range(retries + 1):
        try:
            r = _session().get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True,
                               headers={"User-Agent": USER_AGENT})
            return r.status_code, r.url
        except requests.exceptions.RequestException as e:
            if attempt == retries:
                return "ERR", str(e)[:100]
            time.sleep(0.5 * (attempt + 1))


def run_parity(old_site: str, target: str, resume: bool, limit):
    """For every redirect, confirm the legacy URL resolves (200) on the live old
    site AND the native target resolves (200) on the new site."""
    ob, tb = old_site.rstrip("/"), target.rstrip("/")
    rows = [r for r in read_map_rows() if r["status"] in ("matched", "parent_fallback")]

    # one native per old_url, conflict-resolved like generate
    best: dict[str, dict] = {}
    for r in rows:
        ou = path_only(r["old_url"])
        best[ou] = r if ou not in best else _better(best[ou], r)

    fields = ["old_url", "old_status", "old_final_url", "native_url", "new_status", "verdict"]
    done = {}
    if resume and PARITY_CSV.exists():
        with open(PARITY_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("verdict"):
                    done[row["old_url"]] = row

    todo = [(ou, best[ou]["native_url"]) for ou in sorted(best) if ou not in done]
    if limit:
        todo = todo[:limit]

    # new-target existence: dedupe (many old URLs share a native), check on the new site
    natives = sorted({n for _, n in todo})
    print(f"Checking {len(natives)} native targets on {tb} ...")
    new_status = {}
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        for n, res in zip(natives, ex.map(lambda n: _final_status(tb + n), natives)):
            new_status[n] = res[0]

    # legacy-source existence: check each old URL on the live old site (gentle concurrency)
    print(f"Checking {len(todo)} legacy URLs on {ob} (be patient; polite concurrency) ...")
    old_status = {}
    olds = [ou for ou, _ in todo]
    done_ct = 0
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for ou, res in zip(olds, ex.map(lambda ou: _final_status(ob + ou), olds)):
            old_status[ou] = res
            done_ct += 1
            if done_ct % 250 == 0:
                print(f"  [{done_ct}/{len(olds)}]")

    results = dict(done)
    for ou, native in todo:
        os_code, ofin = old_status.get(ou, ("", ""))
        ns = new_status.get(native, "")
        old_ok, new_ok = (os_code == 200), (ns == 200)
        verdict = ("ok" if old_ok and new_ok else
                   "both_missing" if not old_ok and not new_ok else
                   "old_missing" if not old_ok else "new_missing")
        results[ou] = {"old_url": ou, "old_status": os_code, "old_final_url": ofin,
                       "native_url": native, "new_status": ns, "verdict": verdict}

    with open(PARITY_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows([results[k] for k in sorted(results)])

    summ = Counter(r["verdict"] for r in results.values())
    print(f"\nWrote {PARITY_CSV}")
    for k in sorted(summ):
        print(f"  {k}: {summ[k]}")
    bad = sum(v for k, v in summ.items() if k != "ok")
    if bad:
        print(f"\n{bad} redirects have a missing source or target — see non-ok rows.")


# --- CLI --------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Deterministic legacy->native redirect pipeline.")
    sub = parser.add_subparsers(dest="command")

    b = sub.add_parser("build", help="Build base map from the Hugo manifest")
    b.add_argument("--manifest", default=str(MANIFEST_DEFAULT), help="Path or URL to redirects.json")

    r = sub.add_parser("reconcile", help="Merge old_urls.csv + apply parent-section fallback")
    r.add_argument("--manifest", default=str(MANIFEST_DEFAULT), help="Path or URL to redirects.json")

    t = sub.add_parser("taxonomy", help="Generate utils/taxonomy_redirects.csv from taxonomy_aliases.tsv + manifest")
    t.add_argument("--manifest", default=str(MANIFEST_DEFAULT), help="Path or URL to redirects.json")

    sub.add_parser("generate", help="Emit static/redirects.caddy from the map (Hugo copies it to public/)")

    v = sub.add_parser("verify", help="HTTP-verify redirects against a target")
    v.add_argument("--target", required=True, help="Base URL of running Caddy+Hugo (e.g. http://localhost:8080)")
    v.add_argument("--resume", action="store_true")
    v.add_argument("--limit", type=int, default=None)

    c = sub.add_parser("crosscheck", help="Confirm live old-site /node/{nid} matches recorded alias")
    c.add_argument("--old-site", required=True, help="Base URL of the live old site")
    c.add_argument("--manifest", default=str(MANIFEST_DEFAULT))
    c.add_argument("--resume", action="store_true")
    c.add_argument("--limit", type=int, default=None)

    cr = sub.add_parser("crawl", help="Enumerate old URLs from the old site's sitemap.xml (seam)")
    cr.add_argument("--old-site", required=True)

    pa = sub.add_parser("parity", help="Confirm each legacy URL exists on the old site AND its target exists on the new site")
    pa.add_argument("--old-site", required=True, help="Base URL of the live old site (source)")
    pa.add_argument("--target", required=True, help="Base URL of the new site (target)")
    pa.add_argument("--resume", action="store_true")
    pa.add_argument("--limit", type=int, default=None)

    args = parser.parse_args()
    if args.command == "build":
        run_build(args.manifest)
    elif args.command == "reconcile":
        run_reconcile(args.manifest)
    elif args.command == "taxonomy":
        run_taxonomy(args.manifest)
    elif args.command == "generate":
        run_generate()
    elif args.command == "verify":
        run_verify(args.target, resume=args.resume, limit=args.limit)
    elif args.command == "crosscheck":
        run_crosscheck(args.old_site, args.manifest, resume=args.resume, limit=args.limit)
    elif args.command == "crawl":
        run_crawl(args.old_site)
    elif args.command == "parity":
        run_parity(args.old_site, args.target, resume=args.resume, limit=args.limit)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
