import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from restore_drupal_nodes import (  # noqa: E402
    DrupalClient,
    coalesce_pages,
    entity_to_page,
    local_file_url,
    parse_range,
    public_file_relative,
)


def entity(nid, content_type, title, body="", alias=None):
    data = {
        "nid": [{"value": nid}],
        "type": [{"target_id": content_type}],
        "status": [{"value": True}],
        "title": [{"value": title}],
        "created": [{"value": "2025-11-05T14:20:29+00:00"}],
        "changed": [{"value": "2025-12-04T22:32:55+00:00"}],
        "promote": [{"value": False}],
        "sticky": [{"value": False}],
        "path": [{"alias": alias or f"/node-alias/{nid}"}],
    }
    if body:
        data["field_body"] = [{"value": body}]
    return data


class RestoreDrupalNodesTests(unittest.TestCase):
    def test_public_file_paths_are_local_and_traversal_safe(self):
        source = "https://drupal.example/sites/default/files/2025-11/A%20File.pdf"
        self.assertEqual(public_file_relative(source), "2025-11/A File.pdf")
        self.assertEqual(local_file_url(source), "/files/2025-11/A%20File.pdf")
        self.assertIsNone(public_file_relative("/sites/default/files/../secret"))

    def test_rest_entity_maps_body_images_taxonomy_and_attachment(self):
        data = entity(
            25901,
            "teaching_guides",
            "Guide",
            '<p>Hello</p><img src="/sites/default/files/inline/A%20Photo.jpg">',
            "/teaching-materials/teaching-guides/25901",
        )
        data.update(
            {
                "field_splash_image": [
                    {
                        "target_id": 12,
                        "url": "https://drupal.example/sites/default/files/splash.jpg",
                    }
                ],
                "grade_level": [{"target_id": 45}],
                "topic": [{"target_id": 61}],
                "upload": [
                    {
                        "target_id": 22,
                        "description": "Guide PDF",
                        "display": True,
                        "url": "https://drupal.example/sites/default/files/guide.pdf",
                    }
                ],
            }
        )

        page = entity_to_page(data, {45: "11", 61: "Politics"})

        self.assertIn("/files/inline/A%20Photo.jpg", page.body)
        self.assertEqual(page.frontmatter["splash_image"], "/files/splash.jpg")
        self.assertEqual(page.frontmatter["grade_levels"], ["high"])
        self.assertEqual(page.frontmatter["topics"], ["Politics"])
        self.assertEqual(page.frontmatter["attachments"][0]["url"], "/files/guide.pdf")
        self.assertEqual(page.frontmatter["date"], "2025-11-05T09:20:29")

    def test_btt_pair_becomes_one_page_with_both_redirect_identities(self):
        part1 = entity(25910, "beyond_the_textbook", "Revolution")
        part1["field_textbook_excerpt"] = [{"value": "<p>Textbook view</p>"}]
        part1["field_question"] = [{"value": "What changed?"}]
        part2 = entity(
            25911,
            "beyond_the_textbook_part_2",
            "Revolution",
            "<p>Full essay</p>",
        )
        entities = {25910: part1, 25911: part2}
        pages = coalesce_pages(
            [entity_to_page(part1, {}), entity_to_page(part2, {})], entities
        )

        self.assertEqual(len(pages), 1)
        page = pages[0]
        self.assertEqual(page.nid, 25911)
        self.assertIn("/node/25910", page.frontmatter["aliases"])
        self.assertEqual(page.frontmatter["question"], "What changed?")
        self.assertEqual(page.frontmatter["what_textbooks_say"], "Textbook view")
        self.assertEqual(page.body, "Full essay")

    def test_empty_exact_title_duplicate_moves_alias_to_populated_page(self):
        sparse = entity(25885, "website", "Teaching American History")
        rich = entity(
            25886,
            "website",
            "Teaching American History",
            "<p>Review</p>",
        )
        entities = {25885: sparse, 25886: rich}
        pages = coalesce_pages(
            [entity_to_page(sparse, {}), entity_to_page(rich, {})], entities
        )

        self.assertEqual([page.nid for page in pages], [25886])
        self.assertIn("/node/25885", pages[0].frontmatter["aliases"])

    def test_parse_range_is_inclusive(self):
        self.assertEqual(parse_range("4:6"), [4, 5, 6])

    def test_taxonomy_name_comes_from_public_page_title(self):
        client = DrupalClient("https://drupal.example")
        client._read = lambda url, accept="application/json": (
            b"<html><title>Expansion &amp; Reform, 1801-1861 | "
            b"TeachingHistory.org</title></html>"
        )

        self.assertEqual(
            client.term_name(22), (22, "Expansion & Reform, 1801-1861")
        )


if __name__ == "__main__":
    unittest.main()
