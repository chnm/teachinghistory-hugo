import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


_spec = importlib.util.spec_from_file_location(
    "drupal_field_inventory",
    Path(__file__).resolve().parent.parent / "drupal_field_inventory.py",
)
inventory = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = inventory
_spec.loader.exec_module(inventory)


class DrupalFieldInventoryTests(unittest.TestCase):
    def test_inventory_uses_extractor_mappings_and_counts_multiline_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            extractor = root / "extractor.py"
            extractor.write_text(
                "TEXT_FIELD_TABLES = {'node__field_body': 'field_body'}\n"
                "METADATA_FIELD_TABLES = {}\n"
                "LINK_FIELD_TABLES = {'node__field_website': 'website_links'}\n"
                "FILE_FIELD_TABLES = {}\n"
                "REFERENCE_FIELD_TABLES = {}\n"
                "IMAGE_FIELD_TABLES = {}\n",
                encoding="utf-8",
            )
            sql_dump = root / "fixture.sql"
            sql_dump.write_text(
                "CREATE TABLE `node__field_body` (\n"
                "  `bundle` varchar(128) NOT NULL,\n"
                "  `deleted` tinyint NOT NULL,\n"
                "  `entity_id` int NOT NULL,\n"
                "  `revision_id` int NOT NULL,\n"
                "  `langcode` varchar(32) NOT NULL,\n"
                "  `delta` int NOT NULL,\n"
                "  `field_body_value` longtext NOT NULL\n"
                ") ENGINE=InnoDB;\n"
                "INSERT INTO `node__field_body` VALUES\n"
                "('page',0,1,1,'en',0,'Text with (parentheses)'),\n"
                "('page',0,2,2,'en',0,'It\\'s populated');\n"
                "CREATE TABLE `node__field_website` (\n"
                "  `bundle` varchar(128) NOT NULL,\n"
                "  `field_website_uri` varchar(2048) NOT NULL\n"
                ") ENGINE=InnoDB;\n",
                encoding="utf-8",
            )

            tracked = inventory.load_tracked_tables(extractor)
            rows = {row.table: row for row in inventory.inventory_dump(sql_dump, tracked)}

            self.assertEqual(rows["node__field_body"].rows, 2)
            self.assertEqual(rows["node__field_body"].value_columns, ["field_body_value"])
            self.assertTrue(rows["node__field_website"].present)
            self.assertEqual(rows["node__field_website"].rows, 0)


if __name__ == "__main__":
    unittest.main()
