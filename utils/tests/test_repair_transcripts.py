import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repair_transcripts import repair_transcripts, replace_transcript  # noqa: E402


class TranscriptRepairTests(unittest.TestCase):
    def test_replace_transcript_preserves_following_section(self):
        source = (
            'Intro.\n\n## Transcript\n\nOld transcript.\n\n'
            '## Resources\n\nKeep this.\n'
        )

        updated = replace_transcript(source, '**Speaker:** New transcript.')

        self.assertEqual(
            updated,
            'Intro.\n\n## Transcript\n\n**Speaker:** New transcript.\n\n'
            '## Resources\n\nKeep this.\n',
        )

    def test_repair_uses_drupal_nid_and_respects_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'example.md'
            original = (
                '---\ntitle: Example\ndrupal_nid: 42\n---\n\n'
                'Overview.\n\n## Transcript\n\nOld transcript.\n'
            )
            path.write_text(original, encoding='utf-8')
            fields = {
                42: {
                    'field_transcript_text_items': [{
                        'delta': 0,
                        'value': '<p><strong>Speaker:</strong> Restored.</p>',
                    }],
                },
            }

            dry_run = repair_transcripts(directory, fields, write=False)
            self.assertEqual(dry_run[0][2], 'updated')
            self.assertEqual(path.read_text(encoding='utf-8'), original)

            repaired = repair_transcripts(directory, fields, write=True)
            self.assertEqual(repaired[0][2], 'updated')
            self.assertIn(
                '## Transcript\n\n**Speaker:** Restored.',
                path.read_text(encoding='utf-8'),
            )


if __name__ == '__main__':
    unittest.main()
