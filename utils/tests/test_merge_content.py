import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from merge_content import merge_file  # noqa: E402


class MergeSafetyTests(unittest.TestCase):
    def test_dry_run_is_the_default_and_reports_metadata_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / 'existing.md'
            extracted = Path(tmp) / 'extracted.md'
            existing.write_text('---\ntitle: Existing\n---\n\nBody.\n')
            extracted.write_text(
                '---\ntitle: Existing\nattachments:\n- url: /file.pdf\n'
                '---\n\nDifferent body.\n'
            )

            status = merge_file(existing, extracted)

            self.assertEqual(status, 'would_add_metadata')
            self.assertNotIn('attachments:', existing.read_text())

    def test_nonempty_body_is_preserved_without_explicit_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / 'existing.md'
            extracted = Path(tmp) / 'extracted.md'
            existing.write_text('---\ntitle: Existing\n---\n\nHand-corrected body.\n')
            extracted.write_text('---\ntitle: Existing\nresources:\n- url: /source\n---\n\nFresh extraction.\n')

            status = merge_file(existing, extracted, dry_run=False)

            self.assertEqual(status, 'metadata_only')
            result = existing.read_text()
            self.assertIn('Hand-corrected body.', result)
            self.assertNotIn('Fresh extraction.', result)
            self.assertIn('resources:', result)

    def test_body_replace_requires_explicit_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / 'existing.md'
            extracted = Path(tmp) / 'extracted.md'
            existing.write_text('---\ntitle: Existing\n---\n\nOld body.\n')
            extracted.write_text('---\ntitle: Existing\n---\n\nReviewed body.\n')

            status = merge_file(
                existing, extracted, dry_run=False, replace_body=True
            )

            self.assertEqual(status, 'updated')
            self.assertIn('Reviewed body.', existing.read_text())

    def test_allowed_keys_limit_frontmatter_additions(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / 'existing.md'
            extracted = Path(tmp) / 'extracted.md'
            existing.write_text('---\ntitle: Existing\n---\n\nBody.\n')
            extracted.write_text(
                '---\ntitle: Existing\nattachments:\n- url: /file.pdf\n'
                'producer: Example\n---\n\nBody.\n'
            )

            merge_file(
                existing,
                extracted,
                dry_run=False,
                allowed_keys={'attachments'},
            )

            result = existing.read_text()
            self.assertIn('attachments:', result)
            self.assertNotIn('producer:', result)


if __name__ == '__main__':
    unittest.main()
