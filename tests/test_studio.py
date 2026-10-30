import base64
import copy
import http.client
import io
import json
from pathlib import Path
import sys
import threading
import tomllib
import unittest
import zipfile
import zlib
import struct

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studio import create_project_files, project_zip, hmod_zip, inspect_project, validated_png, Handler, ThreadingHTTPServer
from security.request_policy import session_token

EXAMPLE = {
 'id': 'rafig_test', 'name': 'Test Content', 'author': 'Creator', 'version':'0.2.0',
 'blocks':[{'id':'ruby_block','name':'Ruby Block','template':'minecraft:iron_block',
            'hardness':4.0,'light':3, 'explosion_resistance':8.5, 'requires_tool':True,
            'friction':0.6, 'map_color': 28, 'sounds':'minecraft:amethyst_block'}],
 'items':[{'id':'ruby','name':'Ruby','template':'minecraft:diamond','rarity':'rare','max_stack_size':16}],
 'recipes':[
    {'id':'ruby_block','type':'shaped','result':'rafig_test:ruby_block','count':1,'grid':['rafig_test:ruby']*9},
    {'id':'ruby_unpack','type':'shapeless','result':'rafig_test:ruby','count':9,'grid':['rafig_test:ruby_block']+['']*8},
 ]
}

def mock_png(width=16, height=16):
    def chunk(tag, content):
        return struct.pack('>I', len(content)) + tag + content + struct.pack('>I',zlib.crc32(tag+content)&0xffffffff)
    header = b'\x89PNG\r\n\x1a\n'
    ihdr=chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    pixels=(b'\x00' + b'\xff\x00\x00\xff'*width)*height
    return header + ihdr + chunk(b'IDAT',zlib.compress(pixels)) + chunk(b'IEND', b'')

class GeneratorTests(unittest.TestCase):
    def test_files_match_documented_layout(self):
        modid, files = create_project_files(EXAMPLE)
        self.assertEqual(modid, 'rafig_test')
        manifest=tomllib.loads(files['horizon-mod.toml'].decode())
        self.assertEqual(manifest['api'],'0.2')
        self.assertEqual(manifest['capabilities'], ['registries'])
        self.assertEqual(manifest['side'],'both')
        self.assertEqual(manifest['version'],'0.2.0')
        self.assertIn('data/rafig_test/horizon/block/ruby_block.json',files)
        self.assertIn('data/rafig_test/horizon/item/ruby.json', files)
        self.assertIn('assets/rafig_test/items/ruby.json', files)
        for path, content in files.items():
            if path.endswith('.json'):
                json.loads(content)

    def test_source_zip_wraps_root_directory(self):
        blob=project_zip(EXAMPLE)
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn('rafig_test/horizon-mod.toml',archive.namelist())
            self.assertIn('rafig_test/data/rafig_test/recipe/ruby_block.json',archive.namelist())
            self.assertNotIn('horizon-mod.toml',archive.namelist())

    def test_hmod_is_content_only_zip_with_root_manifest(self):
        blob=hmod_zip(EXAMPLE)
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn('horizon-mod.toml',archive.namelist())
            self.assertIn('data/rafig_test/recipe/ruby_block.json',archive.namelist())
            self.assertNotIn('mod.wasm',archive.namelist())
            self.assertNotIn('rafig_test/horizon-mod.toml',archive.namelist())
        self.assertEqual(blob,hmod_zip(EXAMPLE),'packages should be reproducible')

    def test_disallow_traversal(self):
        for bad in ('../../evil','Bad Mod','mod/thing','', '_hidden'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                create_project_files({**EXAMPLE,'id':bad})

    def test_disallow_duplicate_block_item_ids(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            create_project_files({**EXAMPLE,'items':[{'id':'ruby_block','name':'Conflict'}]})

    def test_disallow_unlisted_template(self):
        with self.assertRaisesRegex(ValueError,'unsupported template'):
            create_project_files({**EXAMPLE,'blocks':[{'id':'b','name':'B','template':'minecraft:unknown'}]})

    def test_disallow_bad_property_values(self):
        for light in (-1,16,'abc', 3.5, True, None):
            with self.subTest(light=light),self.assertRaises(ValueError):
                create_project_files({**EXAMPLE,'blocks':[{'id':'b','name':'B','light':light}]})

    def test_disallow_bad_finite_hardness_and_version(self):
        for hardness in (float('inf'),float('nan'),-3,51):
            with self.subTest(value=hardness),self.assertRaises(ValueError):
                create_project_files({**EXAMPLE,'blocks':[{'id':'b','name':'B','hardness':hardness}]})
        for version in ('1', 'hello', '1.0','1.0.0\ninvalid = true'):
            with self.subTest(value=version),self.assertRaises(ValueError):
                create_project_files({**EXAMPLE,'version':version})

    def test_optional_block_properties_and_item_stack(self):
        _,files=create_project_files(EXAMPLE)
        props=json.loads(files['data/rafig_test/horizon/block/ruby_block.json'])['properties']
        self.assertEqual(props, {'hardness':4., 'light':3, 'explosion_resistance':8.5,'friction':0.6,
                                 'requires_tool':True, 'map_color':28,'sounds':'minecraft:amethyst_block'})
        data=json.loads(files['data/rafig_test/horizon/item/ruby.json'])
        self.assertEqual(data['max_stack_size'],16)

    def test_uses_vanilla_textures_without_bundling_assets(self):
        _,files=create_project_files(EXAMPLE)
        self.assertFalse(any(path.endswith('.png') for path in files))
        model=json.loads(files['assets/rafig_test/models/block/ruby_block.json'])
        self.assertEqual(model['textures']['all'],'minecraft:block/iron_block')

    def test_reject_bogus_texture(self):
        with self.assertRaisesRegex(ValueError, 'PNG'):
            create_project_files({**EXAMPLE,'items':[{'id':'i','name':'I','texture':'data:text/plain;base64,SGVsbG8='}]})

    def test_accepts_real_png_and_rejects_bad_crc(self):
        data=mock_png()
        url='data:image/png;base64,'+base64.b64encode(data).decode()
        self.assertEqual(validated_png(url),data)
        d=copy.deepcopy(EXAMPLE);d['items'][0]['texture']=url
        _,files=create_project_files(d)
        self.assertEqual(files['assets/rafig_test/textures/item/ruby.png'],data)
        bad=bytearray(data);bad[-1]^=1
        with self.assertRaisesRegex(ValueError,'CRC'):
            validated_png('data:image/png;base64,'+base64.b64encode(bad).decode())

    def test_shaped_pattern_matches_official_ruby_example(self):
        _,files=create_project_files(EXAMPLE)
        data=json.loads(files['data/rafig_test/recipe/ruby_block.json'])
        self.assertEqual(data['type'],'minecraft:crafting_shaped')
        self.assertEqual(data['pattern'],['AAA','AAA','AAA'])
        self.assertEqual(data['key'],{'A':'rafig_test:ruby'})
        self.assertEqual(data['result']['id'],'rafig_test:ruby_block')

    def test_shapeless_matches_official_ruby_example(self):
        _,files=create_project_files(EXAMPLE)
        data=json.loads(files['data/rafig_test/recipe/ruby_unpack.json'])
        self.assertEqual(data, {'type':'minecraft:crafting_shapeless',
          'ingredients':['rafig_test:ruby_block'], 'result':{'id':'rafig_test:ruby','count':9}})

    def test_shaped_trim_and_holes(self):
        d=copy.deepcopy(EXAMPLE)
        d['recipes']=[{'id':'cross','type':'shaped','result':'rafig_test:ruby','grid':
            ['','','','', 'rafig_test:ruby_block', '', 'minecraft:stick', '', 'minecraft:stick']}]
        _,files=create_project_files(d)
        recipe=json.loads(files['data/rafig_test/recipe/cross.json'])
        # Row 1: middle block; row 2: stick in left+right, trimmed top row.
        self.assertEqual(recipe['pattern'], [' A ', 'B B'])
        self.assertEqual(recipe['key'], {'A':'rafig_test:ruby_block','B':'minecraft:stick'})

    def test_rejects_bad_recipe(self):
        variations=[{'id':'oops','type':'shaped','result':'rafig_test:ruby','grid':['']*9},
                    {'id':'oops','type':'magic','result':'rafig_test:ruby','grid':['minecraft:stick']*9},
                    {'id':'oops','type':'shapeless','result':'elsewhere:x','grid':['minecraft:stick']*9},
                    {'id':'oops','type':'shapeless','result':'rafig_test:ruby','grid':['evil:unknown']*9},
                    {'id':'oops','type':'shapeless','result':'rafig_test:ruby','count':65,'grid':['minecraft:stick']*9}]
        for bad in variations:
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                create_project_files({**EXAMPLE,'recipes':[bad]})

    def test_reject_duplicate_recipe_ids(self):
        with self.assertRaisesRegex(ValueError,'Duplicate recipe'):
            create_project_files({**EXAMPLE,'recipes':[EXAMPLE['recipes'][0],EXAMPLE['recipes'][0]]})

    def test_preview_file_list(self):
        info=inspect_project(EXAMPLE)
        self.assertTrue(info['ok'])
        self.assertEqual(info['file_count'],len(info['files']))
        self.assertEqual(info['recipes'],2)

class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def post(self,path,payload):
        con=http.client.HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=5)
        token=self.server._studio_session_token if hasattr(self.server,'_studio_session_token') else session_token(self.server)
        con.request('POST',path,body=json.dumps(payload),headers={'Content-Type':'application/json','X-Studio-Token':token})
        res=con.getresponse();code=res.status;headers=dict(res.getheaders());data=res.read();con.close()
        return code,headers,data
    def test_preview_route(self):
        code,headers,data=self.post('/api/preview',EXAMPLE)
        self.assertEqual(code,200)
        self.assertIn('horizon-mod.toml',json.loads(data)['files'])
    def test_hmod_route_and_content_disposition(self):
        code,headers,data=self.post('/api/hmod',EXAMPLE)
        self.assertEqual(code,200)
        self.assertIn('rafig_test.hmod',headers['Content-Disposition'])
        with zipfile.ZipFile(io.BytesIO(data)) as f:
            self.assertIsNone(f.testzip())
    def test_reject_invalid_post(self):
        code,_,data=self.post('/api/export',{**EXAMPLE,'id':'../break'})
        self.assertEqual(code,400)
        self.assertIn('error',json.loads(data))
    def test_get_home_and_unknown_route(self):
        con=http.client.HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=5)
        con.request('GET','/')
        res=con.getresponse()
        self.assertEqual(res.status,200)
        self.assertIn(b'Horizon Studio',res.read())
        con.close()




class I18nTests(unittest.TestCase):
    def test_default_english_and_selectable_russian(self):
        page=(Path(__file__).resolve().parents[1] / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<html lang="en">',page)
        self.assertIn('id="lang-en"',page)
        self.assertIn('id="lang-ru"',page)
        self.assertIn('src="/i18n.js"',page)
        self.assertIn('window.HorizonI18n.init()',page)

    def test_translatable_elements_reference_translation_keys(self):
        import re
        page=(Path(__file__).resolve().parents[1] / 'index.html').read_text(encoding='utf-8')
        script=(Path(__file__).resolve().parents[1] / 'i18n.js').read_text(encoding='utf-8')
        keys=set(re.findall(r'"([A-Za-z][A-Za-z0-9]*)":',script))
        refs=set(re.findall(r'data-i18n(?:-placeholder|-aria-label)?="([A-Za-z][A-Za-z0-9]*)"',page))
        refs.update(re.findall(r"\bt\('([A-Za-z][A-Za-z0-9]*)'",page))
        self.assertTrue(refs)
        self.assertFalse(refs-keys,'Missing translations for '+str(refs-keys))

    def test_translation_dictionary_key_parity(self):
        import re
        script=(Path(__file__).resolve().parents[1] / 'i18n.js').read_text(encoding='utf-8')
        match=re.search(r'const catalog = (\{.*?\});\n  let locale',script,re.S)
        self.assertIsNotNone(match)
        catalog=json.loads(match.group(1))
        self.assertEqual(set(catalog['en']),set(catalog['ru']))
        self.assertGreaterEqual(len(catalog['en']),80)
        self.assertTrue(all(isinstance(value,str) and value for language in catalog.values() for value in language.values()))

    def test_i18n_asset_is_served_with_js_content_type(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            con=http.client.HTTPConnection('127.0.0.1',server.server_address[1],timeout=5)
            con.request('GET','/i18n.js')
            res=con.getresponse()
            self.assertEqual(res.status,200)
            self.assertIn('javascript',res.getheader('Content-Type'))
            self.assertIn(b'HorizonI18n',res.read())
            con.close()
        finally:
            server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
