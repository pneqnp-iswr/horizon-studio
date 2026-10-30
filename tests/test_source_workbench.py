"""Real source round-trip: editable JSON model -> content .hmod archive."""
import io
import json
import struct
import unittest
import zipfile
import zlib

from source_workbench import safe_overrides, import_resource_pack
from studio import create_project_files, hmod_zip


class SourceWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.project = {'id': 'art_studio', 'name': 'Art Studio', 'author': 'Test',
                        'version': '0.6.0', 'description': 'Test project',
                        'blocks': [{'id':'crystal', 'name':'Crystal', 'template':'minecraft:glass'}],
                        'items': [], 'recipes': [], 'structures': []}
        self.model_path = 'assets/art_studio/models/block/crystal.json'

    def test_source_can_override_generated_model(self):
        cube = {'textures': {'all': 'minecraft:block/glass'},
                'elements': [{'from':[2,2,2], 'to':[14,14,14]}]}
        self.project['source_overrides'] = {self.model_path: json.dumps(cube)}
        _, files = create_project_files(self.project)
        self.assertEqual(json.loads(files[self.model_path])['elements'][0]['from'], [2,2,2])
        with zipfile.ZipFile(io.BytesIO(hmod_zip(self.project))) as archive:
            self.assertEqual(json.loads(archive.read(self.model_path))['elements'][0]['to'], [14,14,14])

    def test_disallows_arbitrary_file_override(self):
        for path in ('horizon-mod.toml', '../evil.rs', 'assets/other/models/block/crystal.json'):
            with self.subTest(path=path):
                self.project['source_overrides'] = {path: '{}'}
                with self.assertRaises(ValueError):
                    create_project_files(self.project)

    def test_invalid_model_rejected(self):
        self.project['source_overrides'] = {self.model_path: json.dumps({'elements':[{'from':[0,0,0], 'to': [16]}]})}
        with self.assertRaises(ValueError):
            create_project_files(self.project)

    def test_invalid_json_rejected(self):
        self.project['source_overrides'] = {self.model_path: '{invalid json'}
        with self.assertRaises(ValueError):
            create_project_files(self.project)

    def test_json_source_preserves_other_generated_files(self):
        self.project['source_overrides'] = {self.model_path: json.dumps({'parent': 'minecraft:block/cube_all', 'textures': {'all': 'minecraft:block/glass'}})}
        _, files = create_project_files(self.project)
        self.assertIn('data/art_studio/horizon/block/crystal.json', files)
        self.assertIn('assets/art_studio/lang/en_us.json', files)

    def test_import_licensed_local_pack_does_not_write_files(self):
        # Minimal valid PNG-like test fixture; importer only checks signatures and byte cap.
        png = b'\x89PNG\r\n\x1a\n' + b'test-pixels'
        pack = io.BytesIO()
        with zipfile.ZipFile(pack,'w') as z:
            z.writestr('assets/minecraft/textures/item/diamond.png', png)
        result = import_resource_pack(pack.getvalue())
        self.assertEqual(result['count'], 1)
        self.assertTrue(result['textures']['minecraft:diamond'].startswith('data:image/png;base64,'))
        self.assertTrue(result['local_only'])

    def test_bad_pack_fails(self):
        with self.assertRaises(ValueError):
            import_resource_pack(b'not a ZIP')


if __name__ == '__main__':
    unittest.main()
