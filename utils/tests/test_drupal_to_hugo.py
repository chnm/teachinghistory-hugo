import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from drupal_to_hugo import (  # noqa: E402
    compose_body,
    html_to_md,
    localize_drupal_image_url,
    parse_file_field_insert,
    parse_file_managed_insert,
    parse_link_field_insert,
    public_file_url,
    resolve_attachments,
)


class StructuredFieldTests(unittest.TestCase):
    def test_link_parser_preserves_delta_title_and_uri(self):
        fields = {}
        insert = [
            "INSERT INTO `node__field_websites` VALUES\n",
            "('website',0,42,42,'und',1,'https://example.org/b','Second','a:0:{}'),\n",
            "('website',0,42,42,'und',0,'https://example.org/a','First','a:0:{}');\n",
        ]

        parse_link_field_insert(insert, fields, 'resources', 'node__field_websites')

        self.assertEqual(fields[42]['resources'][0]['delta'], 1)
        self.assertEqual(fields[42]['resources'][0]['title'], 'Second')
        self.assertEqual(fields[42]['resources'][1]['url'], 'https://example.org/a')

    def test_singular_website_keeps_compatibility_url_and_structured_label(self):
        fields = {}
        insert = [
            "INSERT INTO `node__field_website` VALUES "
            "('website',0,42,42,'und',0,'https://example.org','Example','a:0:{}');\n"
        ]

        parse_link_field_insert(
            insert, fields, 'website_links', 'node__field_website'
        )

        self.assertEqual(fields[42]['website_url'], 'https://example.org')
        self.assertEqual(fields[42]['website_links'][0]['title'], 'Example')

    def test_file_parser_resolves_labels_urls_and_order(self):
        fields = {}
        managed = {}
        parse_file_field_insert([
            "INSERT INTO `node__upload` VALUES "
            "('blog',0,7,7,'und',1,12,1,''),"
            "('blog',0,7,7,'und',0,11,1,'Teacher handout');\n"
        ], fields, 'attachments')
        parse_file_managed_insert([
            "INSERT INTO `file_managed` VALUES "
            "(11,1,'handout.pdf','public://docs/handout.pdf','application/pdf',123,1,'en','',1,1),"
            "(12,1,'notes.pdf','public://notes.pdf','application/pdf',456,1,'en','',1,1);\n"
        ], managed)

        resolve_attachments(fields, managed)

        attachments = fields[7]['attachments']
        self.assertEqual([item['delta'] for item in attachments], [0, 1])
        self.assertEqual(attachments[0]['title'], 'Teacher handout')
        self.assertEqual(
            attachments[0]['url'],
            'https://teachinghistory.org/sites/default/files/docs/handout.pdf',
        )
        self.assertEqual(attachments[1]['title'], 'notes.pdf')

    def test_public_file_url_encodes_spaces(self):
        self.assertEqual(
            public_file_url('public://2024-12/Teacher Guide.pdf'),
            'https://teachinghistory.org/sites/default/files/2024-12/Teacher%20Guide.pdf',
        )


class BodyCompositionTests(unittest.TestCase):
    def test_embedded_drupal_image_is_localized_and_keeps_url_encoding(self):
        source = (
            '<p><img alt="Primary source" '
            'src="/sites/default/files/inline-images/A%20File%E2%80%AF1.png"></p>'
        )

        markdown = html_to_md(source)

        self.assertEqual(
            markdown.strip(),
            '![Primary source](/files/inline-images/A%20File%E2%80%AF1.png)',
        )

    def test_external_image_url_is_not_localized(self):
        self.assertEqual(
            localize_drupal_image_url('https://example.org/image.png'),
            'https://example.org/image.png',
        )

    def test_qa_answer_is_not_duplicated(self):
        body, frontmatter = compose_body('ask_a_historian', {
            'field_answer': '<p>The complete answer.</p>',
            'field_question': 'What happened?',
        })

        self.assertEqual(body.count('The complete answer.'), 1)
        self.assertNotIn('---', body)
        self.assertEqual(frontmatter['question'], 'What happened?')

    def test_learn_more_is_structured_not_body_fallback(self):
        body, frontmatter = compose_body('ask_an_educator', {
            'field_answer': '<p>Main answer.</p>',
            'field_learn_more_text': '<p><a href="/more">Further reading</a>.</p>',
        })

        self.assertEqual(body.strip(), 'Main answer.')
        self.assertEqual(frontmatter['more_information'], '[Further reading](/more).')

    def test_research_tool_composes_distinct_sections(self):
        body, _ = compose_body('research_tool', {
            'field_description': '<p>Overview.</p>',
            'field_directions': '<p>Directions.</p>',
            'field_exemplary_practices': '<p>Example.</p>',
        })

        self.assertIn('Overview.', body)
        self.assertIn('## Getting Started', body)
        self.assertIn('Directions.', body)
        self.assertIn('## Examples', body)


if __name__ == '__main__':
    unittest.main()
