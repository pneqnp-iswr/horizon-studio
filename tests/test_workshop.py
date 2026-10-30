"""Horizon Studio 0.4 regression tests: generated outputs, not just UI labels."""
import gzip
import io
import json
from pathlib import Path
import sys
import unittest
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from voxel_architect import generate_structure, serialize_structure, MODES, PALETTES
from studio import create_project_files, hmod_zip
from mod_doctor import audit_project
from test_structures import NbtReader


def spec(**kwargs):
    return {'id':'demo','kind':'floating_island','theme':'stone','size':19,'seed':42, **kwargs}


def project(**kwargs):
    return {'id':'workshop','name':'Workshop','author':'Tester','version':'0.4.0','blocks':[],
            'items':[],'recipes':[],'structures':[], **kwargs}


class Generators04(unittest.TestCase):
    def test_six_generators_and_six_themes(self):
        self.assertEqual(len(MODES),6)
        self.assertEqual(len(PALETTES),6)
        for kind in MODES:
            for theme in PALETTES:
                with self.subTest(kind=kind,theme=theme):
                    vox=generate_structure(spec(kind=kind,theme=theme))
                    self.assertTrue(vox)
                    self.assertEqual(set(vox.values())-set(PALETTES[theme]),set())
    def test_every_new_generator_at_minimum_and_maximum_size(self):
        for kind in ('floating_island','crystal_grove','battle_arena'):
            for size in (7,29):
                vox=generate_structure(spec(kind=kind,size=size))
                self.assertTrue(all(0<=x<32 and 0<=y<32 and 0<=z<32 for x,y,z in vox))
                self.assertLessEqual(len(vox),12000)
    def test_rotation_coordinates_match_exported_model(self):
        source=generate_structure(spec())
        size=19
        for angle,convert in ((90,lambda x,z:(z,size-1-x)),
                              (180,lambda x,z:(size-1-x,size-1-z)),
                              (270,lambda x,z:(size-1-z,x))):
            rotated=generate_structure(spec(rotation=angle))
            self.assertEqual(rotated,{(*convert(x,z)[:1],y,convert(x,z)[1]):block for (x,y,z),block in source.items()})
    def test_mirror_is_exact_and_does_not_change_blocks(self):
        source=generate_structure(spec(kind='battle_arena'))
        self.assertEqual(generate_structure(spec(kind='battle_arena',mirror='x')),
                         {(18-x,y,z):b for (x,y,z),b in source.items()})
        self.assertEqual(generate_structure(spec(kind='battle_arena',mirror='z')),
                         {(x,y,18-z):b for (x,y,z),b in source.items()})
    def test_rotation_and_mirror_preserve_nbt_structure(self):
        vox=generate_structure(spec(rotation=270,mirror='z',theme='end'))
        nbt=NbtReader(gzip.decompress(serialize_structure(vox))).parse()
        self.assertEqual(len(nbt['blocks']),len(vox))
        self.assertEqual(len(nbt['palette']),len(set(vox.values())))
    def test_reproducibility_new_generators(self):
        for kind in ('floating_island','crystal_grove','battle_arena'):
            self.assertEqual(serialize_structure(generate_structure(spec(kind=kind))),
                             serialize_structure(generate_structure(spec(kind=kind))))
    def test_seed_affects_crystal_and_island(self):
        for kind in ('floating_island','crystal_grove'):
            self.assertNotEqual(generate_structure(spec(kind=kind,seed=1)),generate_structure(spec(kind=kind,seed=2)))
    def test_invalid_rotation_or_mirror(self):
        for changes in ({'rotation':45},{'rotation':True},{'rotation':90.0},
                        {'rotation':'90'},{'mirror':'other'},{'mirror':[]}, {'mirror':None}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                generate_structure(spec(**changes))


class Content04(unittest.TestCase):
    def test_russian_names_exported_with_fallback(self):
        req=project(blocks=[{'id':'lamp','name':'Lantern','name_ru':'Фонарь','template':'minecraft:glass'}],
                    items=[{'id':'gem','name':'Gem','template':'minecraft:diamond'}])
        _,files=create_project_files(req)
        en=json.loads(files['assets/workshop/lang/en_us.json'])
        ru=json.loads(files['assets/workshop/lang/ru_ru.json'])
        self.assertEqual(en['block.workshop.lamp'],'Lantern')
        self.assertEqual(ru['block.workshop.lamp'],'Фонарь')
        self.assertEqual(ru['item.workshop.gem'],'Gem')
    def test_mining_tags_and_tiers_exported(self):
        req=project(blocks=[
            {'id':'ore','name':'Ore','template':'minecraft:iron_block','requires_tool':True,
             'mining_tool':'pickaxe','tool_tier':'iron'},
            {'id':'wood','name':'Wood','template':'minecraft:oak_planks','mining_tool':'axe'},
        ])
        _,files=create_project_files(req)
        def tag(name):return json.loads(files['data/minecraft/tags/block/'+name+'.json'])
        self.assertEqual(tag('mineable/pickaxe')['values'],['workshop:ore'])
        self.assertEqual(tag('needs_iron_tool')['values'],['workshop:ore'])
        self.assertEqual(tag('mineable/axe')['values'],['workshop:wood'])
        self.assertFalse(tag('mineable/pickaxe')['replace'])
    def test_legacy_tool_required_defaults_to_pickaxe(self):
        _,files=create_project_files(project(blocks=[{'id':'ore','name':'Ore','requires_tool':True}]))
        self.assertIn('data/minecraft/tags/block/mineable/pickaxe.json',files)
    def test_invalid_mining_settings(self):
        for entry in ({'mining_tool':'laser'}, {'tool_tier':'iron','mining_tool':'none'},
                      {'tool_tier':'wood'}, {'mining_tool':False}):
            with self.subTest(entry=entry),self.assertRaises(ValueError):
                create_project_files(project(blocks=[{'id':'x','name':'X',**entry}]))
    def test_hmod_contains_real_structures_tags_and_languages(self):
        req=project(structures=[spec(kind='crystal_grove',rotation=90,theme='quartz')],
                    blocks=[{'id':'ore','name':'Ore','requires_tool':True,'name_ru':'Руда'}])
        archive=hmod_zip(req)
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            self.assertIsNone(z.testzip())
            self.assertIn('assets/workshop/lang/ru_ru.json',z.namelist())
            self.assertIn('data/minecraft/tags/block/mineable/pickaxe.json',z.namelist())
            self.assertIn('data/workshop/structure/demo.nbt',z.namelist())
            self.assertEqual(NbtReader(gzip.decompress(z.read('data/workshop/structure/demo.nbt'))).parse()['entities'],[])
    def test_reproducible_packaging(self):
        req=project(structures=[spec(kind='crystal_grove',rotation=180,mirror='x')])
        self.assertEqual(hmod_zip(req),hmod_zip(req))


class ModDoctor04(unittest.TestCase):
    def test_doctor_reports_export_error_without_crashing(self):
        info=audit_project(project(blocks=[{'id':'../escape','name':'X'}]))
        self.assertFalse(info['ok'])
        self.assertEqual(info['issues'][0]['code'],'EXPORT_VALIDATION_FAILED')
    def test_doctor_success_contains_stats(self):
        info=audit_project(project(structures=[spec()]))
        self.assertTrue(info['ok'])
        self.assertTrue(info['stats']['files']>=4)
        self.assertIn('STRUCTURE_PLACEMENT',[x['code'] for x in info['issues']])
    def test_doctor_catches_crafting_bootstrap(self):
        req=project(items=[{'id':'a','name':'A'},{'id':'b','name':'B'}],recipes=[
            {'id':'a_from_b','type':'shapeless','result':'workshop:a','grid':['workshop:b']+['']*8},
            {'id':'b_from_a','type':'shapeless','result':'workshop:b','grid':['workshop:a']+['']*8},
        ])
        codes=[x['code'] for x in audit_project(req)['issues']]
        self.assertEqual(codes.count('CRAFT_BOOTSTRAP'),2)
    def test_doctor_handles_crafting_base_recipe(self):
        req=project(items=[{'id':'a','name':'A'},{'id':'b','name':'B'}],recipes=[
            {'id':'make_a','type':'shapeless','result':'workshop:a','grid':['minecraft:diamond']+['']*8},
            {'id':'make_b','type':'shapeless','result':'workshop:b','grid':['workshop:a']+['']*8},
        ])
        info=audit_project(req)
        self.assertEqual(info['stats']['craftable_from_vanilla'],2)
        self.assertNotIn('CRAFT_BOOTSTRAP',[x['code'] for x in info['issues']])
    def test_doctor_detects_colliding_recipe_patterns(self):
        req=project(items=[{'id':'a','name':'A'}, {'id':'b','name':'B'}],recipes=[
            {'id':'first','type':'shaped','result':'workshop:a','grid':['minecraft:diamond']+['']*8},
            {'id':'second','type':'shaped','result':'workshop:b','grid':['']*4+['minecraft:diamond']+['']*4},
        ])
        self.assertIn('RECIPE_CONFLICT',[x['code'] for x in audit_project(req)['issues']])

if __name__=='__main__':unittest.main()

class CommandLine04(unittest.TestCase):
    def test_offline_build_matches_editor_bytes(self):
        import tempfile
        from horizon_cli import main, load_project
        data={'format':'horizon-studio','schema':3,
              'metadata':{'id':'cli_demo','name':'CLI Demo','author':'Tester'},
              'blocks':[],'items':[{'id':'gem','name':'Gem'}],
              'recipes':[{'id':'gem_recipe','type':'shapeless','grid':['minecraft:diamond']+['']*8,
                          'result':'@gem','count':1}], 'structures':[]}
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            inp=base/'demo.hstudio.json';out=base/'demo.hmod'
            inp.write_text(json.dumps(data),encoding='utf-8')
            self.assertEqual(main(['build',str(inp),'--output',str(out)]),0)
            self.assertEqual(out.read_bytes(),hmod_zip(load_project(inp)))
            with zipfile.ZipFile(out) as z:
                recipe=json.loads(z.read('data/cli_demo/recipe/gem_recipe.json'))
                self.assertEqual(recipe['result']['id'],'cli_demo:gem')
    def test_cli_rejects_corrupt_input_without_writing_files(self):
        import tempfile
        from horizon_cli import main
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);inp=base/'bad.hstudio.json';out=base/'bad.hmod'
            inp.write_text('not json',encoding='utf-8')
            import contextlib
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['build',str(inp),'-o',str(out)]),1)
            self.assertFalse(out.exists())

class DoctorHttp04(unittest.TestCase):
    def test_doctor_endpoint_success_and_validation_error(self):
        import http.client
        import threading
        from http.server import ThreadingHTTPServer
        from studio import Handler
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        t=threading.Thread(target=server.serve_forever,daemon=True)
        t.start()
        try:
            for req,ok in ((project(items=[{'id':'a','name':'A'}]),True),
                           (project(items=[{'id':'not-good','name':'A'}]),False)):
                connection=http.client.HTTPConnection('127.0.0.1',server.server_address[1],timeout=5)
                connection.request('POST','/api/doctor',json.dumps(req),{'Content-Type':'application/json'})
                r=connection.getresponse()
                self.assertEqual(r.status,200)
                response=json.loads(r.read())
                self.assertIs(response['ok'],ok)
                connection.close()
        finally:
            server.shutdown();server.server_close();t.join()
