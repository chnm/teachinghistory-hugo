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

The authoritative map is the Hugo build artifact `public/redirects.json` (emitted by
layouts/index.redirects.json). See docs in that template and utils/relocate_urls.py.

Subcommands:
    build       Read the Hugo manifest -> base legacy->native map (utils/redirect_map.csv).
    reconcile   Merge externally-discovered old URLs (utils/old_urls.csv) and apply the
                parent-section fallback to anything unmatched. Rewrites redirect_map.csv.
    generate    Emit teachinghistory-website/redirects.caddy (a `map` block, 301s).
    verify      HTTP-check every mapping against a running target (Caddy+Hugo).
    crosscheck  Oracle: for each nid, confirm the LIVE old site's /node/{nid} 301s to the
                alias we recorded (no sitemap needed). QA only; does not change the map.
    crawl       CMS-agnostic seam: enumerate old URLs from the old site's sitemap.xml.

Usage:
    uv run utils/redirect_mapper.py build
    uv run utils/redirect_mapper.py reconcile
    uv run utils/redirect_mapper.py generate
    uv run utils/redirect_mapper.py verify --target http://localhost:8080
    uv run utils/redirect_mapper.py crosscheck --old-site https://teachinghistory.org --limit 200
    uv run utils/redirect_mapper.py crawl --old-site https://example.org

Pluggable seams for other CMSes:
    * map source        -> load_manifest() (any Hugo site emits the same manifest shape)
    * identity extractor -> EXTRACTORS[cms] (Drupal here needs none; nid comes from the manifest)
    * URL enumerator    -> run_crawl() (sitemap parsing is generic; add per-CMS fallbacks)
"""

import argparse
import concurrent.futures as cf
import csv
import json
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
CROSSCHECK_CSV = OUTPUT_DIR / "redirect_crosscheck.csv"
VERIFY_CSV = OUTPUT_DIR / "redirect_verify.csv"
PARITY_CSV = OUTPUT_DIR / "redirect_parity.csv"
CADDY_OUT = WEBSITE_DIR / "redirects.caddy"

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

def run_build(manifest_src):
    manifest = load_manifest(manifest_src)
    pages = manifest.get("pages", [])
    rows = []
    for pg in pages:
        native = pg["native"]
        nid = pg.get("nid")
        src = pg.get("source_file", "")
        for legacy in pg.get("legacy_paths", []):
            rows.append({
                "old_url": path_only(legacy),
                "native_url": native,
                "match_via": "node" if is_node_path(legacy) else "alias",
                "nid": "" if nid is None else nid,
                "source_file": src,
                "status": "matched",
                "notes": "",
            })
    write_map_rows(rows)
    aliases = sum(1 for r in rows if r["match_via"] == "alias")
    nodes = sum(1 for r in rows if r["match_via"] == "node")
    print(f"Built {len(rows)} legacy->native pairs from {len(pages)} pages.")
    print(f"  alias paths: {aliases}")
    print(f"  node paths:  {nodes}")
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
    nid_index = {}
    path_index = {}
    for pg in manifest.get("pages", []):
        native = pg["native"]
        if pg.get("nid") is not None:
            nid_index[str(pg["nid"])] = native
        for legacy in pg.get("legacy_paths", []):
            path_index[norm(legacy)] = native

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

    write_map_rows(rows)
    print(f"Reconciled. Learned prefix remaps: {remap or '(none)'}")
    print(f"  external old URLs considered: {len(old_urls)} (new: {added})")
    print(f"  newly matched: {matched} | parent-fallback: {fallback}")
    print(f"Map now has {len(rows)} rows -> {MAP_CSV}")
    if not old_urls:
        print("Note: no utils/old_urls.csv found (no sitemap on this site) — map = manifest only.")


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

    # nid -> (expected alias, native) from the manifest
    targets = []
    for pg in manifest.get("pages", []):
        if pg.get("nid") is None:
            continue
        aliases = [path_only(l) for l in pg.get("legacy_paths", []) if not is_node_path(l)]
        targets.append((str(pg["nid"]), aliases, pg["native"]))

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

    sub.add_parser("generate", help="Emit redirects.caddy from the map")

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
