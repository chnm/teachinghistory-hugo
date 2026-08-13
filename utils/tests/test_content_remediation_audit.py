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
            self.assertIn("duplicate_body", rows[0]["Audit Flags"])
            self.assertIn("missing_asset:thumbnail", rows[0]["Audit Flags"])


if __name__ == "__main__":
    unittest.main()
