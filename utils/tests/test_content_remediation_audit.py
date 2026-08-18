import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


_spec = importlib.util.spec_from_file_location(
    "content_remediation_audit",
    Path(__file__).resolve().parent.parent / "content_remediation_audit.py",
)
audit = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = audit
_spec.loader.exec_module(audit)


def write_page(content_dir, relative_path, frontmatter, body):
    path = content_dir / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = "\n".join(f"{key}: {value}" for key, value in frontmatter.items())
    path.write_text(f"---\n{fields}\n---\n\n{body}\n", encoding="utf-8")
    return path


class ContentRemediationAuditTests(unittest.TestCase):
    def test_representative_tracker_pages_resolve_by_nid_and_legacy_url(self):
        repo_root = Path(__file__).resolve().parents[2]
        content_dir = repo_root / "teachinghistory-website" / "content"
        fixture_path = Path(__file__).parent / "fixtures" / "content_remediation_pages.csv"
        by_route, by_nid = audit.build_content_index(content_dir)

        with fixture_path.open(newline="", encoding="utf-8") as handle:
            fixtures = list(csv.DictReader(handle))

        self.assertEqual(len(fixtures), 11)
        for fixture in fixtures:
            nid = fixture["Drupal NID"]
            with self.subTest(nid=nid):
                self.assertEqual(by_nid[nid].relative_path, fixture["Content File"])
                page = audit.resolve_page(fixture["Legacy URL"], by_route, by_nid)
                self.assertIsNotNone(page)
                self.assertEqual(page.drupal_nid, nid)

    def test_defect_layer_distinguishes_source_rendering_and_external_work(self):
        self.assertEqual(
            audit.defect_layer({"Workstream": "Images", "Status": "Resolved"}),
            "Source extraction / asset mapping",
        )
        self.assertEqual(
            audit.defect_layer({"Workstream": "Site chrome", "Status": "Resolved"}),
            "Hugo rendering",
        )
        self.assertEqual(
            audit.defect_layer({"Workstream": "Video", "Status": "In progress"}),
            "External media migration",
        )
        self.assertEqual(
            audit.defect_layer({"Workstream": "Body content", "Status": "Duplicate"}),
            "Tracker duplicate",
        )

    def test_normalize_url_path_removes_host_fragment_and_trailing_slash(self):
        self.assertEqual(
            audit.normalize_url_path(" https://dev.example.org/section/page/#notes "),
            "/section/page",
        )
        self.assertEqual(audit.normalize_url_path("section/page/"), "/section/page")

    def test_content_index_resolves_frontmatter_nid_and_slug_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            content_dir = Path(tmp) / "content"
            write_page(
                content_dir,
                "section/an-example-123.md",
                {"url": "/section/123", "drupal_nid": "123"},
                "A substantial body. " * 30,
            )
            by_route, by_nid = audit.build_content_index(content_dir)

            self.assertEqual(
                audit.resolve_page("https://dev.example.org/section/123/", by_route, by_nid).drupal_nid,
                "123",
            )
            self.assertEqual(
                audit.resolve_page("https://dev.example.org/section/an-example/", by_route, by_nid).drupal_nid,
                "123",
            )

    def test_content_index_resolves_multiline_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            content_dir = Path(tmp) / "content"
            path = content_dir / "about" / "_index.md"
            path.parent.mkdir(parents=True)
            path.write_text(
                "---\ntitle: About\naliases:\n  - /about/staff/\n---\n\nAbout us.\n",
                encoding="utf-8",
            )

            by_route, by_nid = audit.build_content_index(content_dir)

            page = audit.resolve_page("https://dev.example.org/about/staff/", by_route, by_nid)
            self.assertIsNotNone(page)
            self.assertEqual(page.relative_path, "about/_index.md")

    def test_has_duplicate_body_detects_repeated_substantial_sections(self):
        section = "This is repeated migrated content with enough text to be substantial. " * 8
        self.assertTrue(audit.has_duplicate_body(f"{section}\n\n---\n\n{section}"))
        different = "Different supporting material with enough text to be substantial. " * 8
        self.assertFalse(audit.has_duplicate_body(f"{section}\n\n---\n\n{different}"))

    def test_audit_tracker_reports_match_duplicate_and_missing_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content_dir = root / "content"
            static_dir = root / "static"
            static_dir.mkdir()
            repeated = "Repeated answer text for the migrated page. " * 10
            write_page(
                content_dir,
                "digital/example-24089.md",
                {
                    "url": "/digital/24089",
                    "drupal_nid": "24089",
                    "thumbnail": "/files/missing.jpg",
                },
                f"{repeated}\n\n---\n\n{repeated}",
            )
            tracker = root / "tracker.csv"
            with tracker.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["ID", "URL", "Status", "Workstream"])
                writer.writeheader()
                writer.writerow({
                    "ID": "TH-001",
                    "URL": "https://dev.example.org/digital/24089/",
                    "Status": "Open",
                    "Workstream": "Body content",
                })

            rows = audit.audit_tracker(tracker, content_dir, static_dir)

            self.assertEqual(rows[0]["Content File"], "digital/example-24089.md")
            self.assertEqual(rows[0]["Drupal NID"], "24089")
            self.assertEqual(
                rows[0]["Defect Layer"],
                "Source extraction + Hugo rendering",
            )
            self.assertIn("duplicate_body", rows[0]["Audit Flags"])
            self.assertIn("missing_asset:thumbnail", rows[0]["Audit Flags"])

    def test_audit_flags_missing_and_case_mismatched_local_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content_dir = root / "content"
            static_dir = root / "static"
            (static_dir / "files").mkdir(parents=True)
            (static_dir / "files" / "Source.JPG").write_bytes(b"fixture")
            page_path = write_page(
                content_dir,
                "section/example.md",
                {"thumbnail": "/files/source.jpg"},
                "A substantial body. " * 30
                + "\n\n[Handout](/files/missing.pdf)",
            )
            page = audit.parse_content_file(page_path, content_dir)

            flags = audit.audit_flags(page, static_dir)

            self.assertIn("case_mismatched_asset:thumbnail", flags)
            self.assertIn("missing_local_file:/files/missing.pdf", flags)


if __name__ == "__main__":
    unittest.main()
