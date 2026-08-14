import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fetch_images import (  # noqa: E402
    audit_content_images,
    normalize_url,
    parse_frontmatter,
    scan_content,
    rewrite_audit_paths,
    rewrite_inline_paths,
)


class ImageMigrationTests(unittest.TestCase):
    def test_frontmatter_delimiter_must_be_its_own_line(self):
        frontmatter, body = parse_frontmatter(
            '---\ntitle: Example\nimage: /files/pic---name.jpg\n---\nBody\n'
        )

        self.assertEqual(frontmatter['image'], '/files/pic---name.jpg')
        self.assertEqual(body, 'Body\n')

    def test_normalize_repairs_system_path_and_cachebuster(self):
        _, system_path = normalize_url(
            '/system/files/image-blog-apa2011-2.jpg'
        )
        _, doubled_path = normalize_url(
            '/files//files/image-blog-apa2011-2.jpg'
        )
        _, cachebusted_path = normalize_url(
            '/files/image-blog-copy5.jpg%3F1301077376'
        )

        self.assertEqual(system_path, 'image-blog-apa2011-2.jpg')
        self.assertEqual(doubled_path, 'image-blog-apa2011-2.jpg')
        self.assertEqual(cachebusted_path, 'image-blog-copy5.jpg')

    def test_scanner_recovers_markdown_destinations_with_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = Path(tmp) / 'content'
            content.mkdir()
            page = content / 'guide.md'
            page.write_text(
                '---\ntitle: Guide\n---\n\n'
                '![Document](/files/inline-images/A File.png)\n',
                encoding='utf-8',
            )

            _, inline = scan_content(content)

            self.assertIn('/files/inline-images/A File.png', inline)

    def test_scanner_excludes_optional_markdown_image_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = Path(tmp) / 'content'
            content.mkdir()
            page = content / 'guide.md'
            page.write_text(
                '---\ntitle: Guide\n---\n\n'
                '![Document](/files/A File.png "A descriptive title")\n',
                encoding='utf-8',
            )

            _, inline = scan_content(content)

            self.assertIn('/files/A File.png', inline)
            self.assertNotIn(
                '/files/A File.png "A descriptive title"', inline
            )

    def test_rewrite_encodes_local_image_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / 'guide.md'
            old = '/sites/default/files/inline-images/A%20File.png'
            page.write_text(f'![Document]({old})\n', encoding='utf-8')

            rewritten = rewrite_inline_paths(
                {old: {str(page)}},
                {old: 'inline-images/A File.png'},
            )

            self.assertEqual(rewritten, 1)
            self.assertIn(
                '/files/inline-images/A%20File.png',
                page.read_text(encoding='utf-8'),
            )

    def test_audit_distinguishes_missing_case_mismatch_and_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content = root / 'content'
            static = root / 'static'
            content.mkdir()
            (static / 'files').mkdir(parents=True)
            (static / 'files' / 'Photo.JPG').write_bytes(b'image')

            (content / 'case.md').write_text(
                '---\ntitle: Case\nimage: /files/photo.jpg\n---\n',
                encoding='utf-8',
            )
            (content / 'missing.md').write_text(
                '---\ntitle: Missing\nimage: /files/missing.jpg\n---\n',
                encoding='utf-8',
            )
            (content / 'fallback.md').write_text(
                '---\ntitle: Fallback\n---\n', encoding='utf-8'
            )

            rows = audit_content_images(content, static)
            statuses = {row['title']: row['status'] for row in rows}

            self.assertEqual(statuses['Case'], 'case_mismatch')
            self.assertEqual(statuses['Missing'], 'missing')
            self.assertEqual(statuses['Fallback'], 'fallback_no_image')

            changed = rewrite_audit_paths(rows, static)

            self.assertEqual(changed, 1)
            self.assertIn(
                '/files/Photo.JPG',
                (content / 'case.md').read_text(encoding='utf-8'),
            )

    def test_audit_recovers_stale_author_path_from_fid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content = root / 'content'
            static = root / 'static'
            content.mkdir()
            (static / 'files' / 'author_image').mkdir(parents=True)
            (static / 'files' / 'author_image' / 'Real.jpg').write_bytes(
                b'image'
            )
            page = content / 'author.md'
            page.write_text(
                '---\ntitle: Author\n'
                'author_image_fid: 12\n'
                'author_image: /files/author_image/truncated\n---\n',
                encoding='utf-8',
            )

            rows = audit_content_images(
                content, static, {12: 'author_image/Real.jpg'}
            )
            author_row = next(row for row in rows if row['usage'] == 'author')

            self.assertEqual(author_row['status'], 'fid_recoverable')
            self.assertEqual(rewrite_audit_paths(rows, static), 1)
            self.assertIn(
                '/files/author_image/Real.jpg',
                page.read_text(encoding='utf-8'),
            )


if __name__ == '__main__':
    unittest.main()
