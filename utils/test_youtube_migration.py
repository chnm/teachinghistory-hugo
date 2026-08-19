from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import youtube_migration as migration


class YouTubeMigrationTests(unittest.TestCase):
    def test_youtube_id_is_derived_from_manifest_url(self) -> None:
        cases = {
            "https://youtu.be/-HVqvzNRvps": "-HVqvzNRvps",
            "https://www.youtube.com/watch?v=abcDEF_123-": "abcDEF_123-",
            "https://www.youtube.com/embed/abcDEF_123-": "abcDEF_123-",
            "https://youtube.com/shorts/abcDEF_123-?feature=share": "abcDEF_123-",
            "https://youtube.com/live/abcDEF_123-": "abcDEF_123-",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(migration.youtube_id_from_url(url), expected)

    def test_invalid_youtube_url_has_no_id(self) -> None:
        self.assertEqual(migration.youtube_id_from_url("https://example.com/video"), "")
        self.assertEqual(migration.youtube_id_from_url("https://youtu.be/short"), "")

    def test_my_lai_duplicate_transcript_is_skipped(self) -> None:
        source = {index: f"Transcript {index}" for index in range(1, 6)}
        self.assertEqual(
            migration.normalized_transcript_positions("24171", source),
            {
                1: "Transcript 1",
                2: "Transcript 2",
                3: "Transcript 4",
                4: "Transcript 5",
            },
        )

    def test_legacy_unicode_line_separators_are_yaml_safe(self) -> None:
        self.assertEqual(
            migration.sanitize_transcript_markdown("first\u2028second\u2029third\u0085fourth"),
            "first\nsecond\nthird\nfourth",
        )

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

    def test_transcript_moves_into_corresponding_video_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page.md"
            path.write_text(
                "---\ntitle: Test\nvideos:\n"
                "- src: /files/Clip1.mp4\n  title: First\n"
                "- src: /files/Clip2.mp4\n  title: Second\n"
                "---\n\nIntro\n\n## Transcript\n\nOld combined transcript.\n",
                encoding="utf-8",
            )
            updated, _ = migration.replace_video_block(
                path,
                [
                    {"clip_index": "1", "asset_name": "Clip1", "youtube_id": "abc123"},
                    {"clip_index": "2", "asset_name": "Clip2", "youtube_id": "def456"},
                ],
                {1: "**Speaker:** First clip.", 2: "**Speaker:** Second clip."},
            )
            self.assertIn("transcript: |-", updated)
            self.assertIn("**Speaker:** First clip.", updated)
            self.assertIn("**Speaker:** Second clip.", updated)
            self.assertNotIn("Old combined transcript.", updated)
            self.assertTrue(updated.rstrip().endswith("Intro"))

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
            self.assertNotIn("/files/Clip1.mp4", updated)
            self.assertIn("Transcript", updated)
            self.assertIn("promoted legacy body video markup", notes[0])


if __name__ == "__main__":
    unittest.main()
