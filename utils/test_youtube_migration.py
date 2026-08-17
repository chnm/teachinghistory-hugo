from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import youtube_migration as migration


class YouTubeMigrationTests(unittest.TestCase):
    def test_proposed_title_respects_youtube_limit(self) -> None:
        title, warning = migration.proposed_title(
            {
                "canonical_page_url": "/best-practices/examples-of-historical-thinking/1",
                "page_title": "A Very Long Historical Thinking Page Title " * 3,
                "clip_title": "A Specific Clip",
                "asset_name": "clip1",
            }
        )
        self.assertLessEqual(len(title), 100)
        self.assertIn("shortened", warning)

    def test_structured_video_block_becomes_youtube_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page.md"
            path.write_text(
                "---\ntitle: Test\nvideos:\n"
                "- src: /files/Clip1.mp4\n  thumb: /files/Clip1.jpg\n  title: First\n"
                "---\n\nBody\n",
                encoding="utf-8",
            )
            updated, notes = migration.replace_video_block(
                path,
                [{"clip_index": "1", "asset_name": "Clip1", "youtube_id": "abc123"}],
            )
            self.assertIn("youtube_id: abc123", updated)
            self.assertNotIn("src: /files/Clip1.mp4", updated)
            self.assertIn("thumb: /files/Clip1.jpg", updated)
            self.assertEqual(notes, [])

    def test_body_video_markup_is_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page.md"
            path.write_text(
                "---\ntitle: Body Test\n---\n\n"
                "/files/Clip1.mp4\n\nvideo/mp4\n\n"
                "[![First](/files/Clip1.jpg)](/files/Clip1.mp4)\n\nTranscript\n",
                encoding="utf-8",
            )
            updated, notes = migration.replace_video_block(
                path,
                [{"clip_index": "1", "asset_name": "Clip1", "youtube_id": "abc123"}],
            )
            self.assertIn("videos:\n- youtube_id: abc123", updated)
            self.assertNotIn("video/mp4", updated)
            self.assertNotIn("](/files/Clip1.mp4)", updated)
            self.assertIn("Transcript", updated)
            self.assertIn("promoted legacy body video markup", notes[0])


if __name__ == "__main__":
    unittest.main()
