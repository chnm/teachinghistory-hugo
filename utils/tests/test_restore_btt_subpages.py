import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from restore_btt_subpages import (  # noqa: E402
    content_inventory,
    extract_btt_subpages,
    serialize_data,
)


class RestoreBttSubpagesTests(unittest.TestCase):
    def test_extracts_sources_bibliographies_and_local_image(self):
        entity = {
            "nid": [{"value": 25913}],
            "field_source1_title": [{"value": "<p>Catawba <em>Map</em></p>"}],
            "field_source1_annotation": [{"value": "<p>Context</p>"}],
            "field_source1_text": [{"value": "<p>Transcript</p>"}],
            "field_source1_citation": [
                {
                    "value": '<p>Library <a href="/files/source1.pdf">scan</a></p>'
                }
            ],
            "field_source1_image": [
                {
                    "url": "https://drupal.example/sites/default/files/CatawbaMap.jpg",
                    "alt": "",
                    "width": 100,
                    "height": 80,
                }
            ],
            "field_secondary_annotated_bib": [
                {"value": "<p>Book <em>Title</em></p>"}
            ],
        }

        data, assets = extract_btt_subpages(entity)

        self.assertEqual(data["nid"], 25913)
        self.assertEqual(len(data["primary_sources"]), 1)
        source = data["primary_sources"][0]
        self.assertEqual(source["title"], "Catawba Map")
        self.assertEqual(source["annotation"], "Context")
        self.assertEqual(source["text"], "Transcript")
        self.assertEqual(source["citation"], "Library [scan](/files/source1.pdf)")
        self.assertEqual(source["image"]["url"], "/files/CatawbaMap.jpg")
        self.assertEqual(source["image"]["alt"], "Catawba Map")
        self.assertEqual(data["bibliographies"][0]["subpage"], 8)
        self.assertIn(
            "https://drupal.example/sites/default/files/CatawbaMap.jpg", assets
        )
        self.assertIn("/files/source1.pdf", assets)

    def test_supports_sixth_source_and_both_bibliographies(self):
        entity = {
            "nid": [{"value": 25059}],
            "field_source6_title": [{"value": "Source Six"}],
            "field_primary_annotated_biblio": [{"value": "Primary"}],
            "field_secondary_annotated_bib": [{"value": "Secondary"}],
        }

        data, _ = extract_btt_subpages(entity)

        self.assertEqual(data["primary_sources"][0]["subpage"], 6)
        self.assertEqual(
            [item["subpage"] for item in data["bibliographies"]], [7, 8]
        )

    def test_inventory_only_selects_surviving_part_two_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "essay.md").write_text(
                "---\ncontent_type: beyond_the_textbook_part_2\n"
                "drupal_nid: 10\n---\nEssay\n",
                encoding="utf-8",
            )
            (root / "part-one.md").write_text(
                "---\ncontent_type: beyond_the_textbook\n"
                "drupal_nid: 9\n---\nSummary\n",
                encoding="utf-8",
            )

            records = content_inventory(root)

        self.assertEqual([(path.name, nid) for path, nid in records], [("essay.md", 10)])

    def test_serialization_uses_literal_blocks_for_markdown(self):
        rendered = serialize_data(
            {
                "nid": 1,
                "primary_sources": [
                    {"subpage": 1, "title": "Source", "text": "One\n\nTwo"}
                ],
                "bibliographies": [],
            }
        )

        self.assertIn("text: |-", rendered)


if __name__ == "__main__":
    unittest.main()
