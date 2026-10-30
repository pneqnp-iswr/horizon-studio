"""No external game assets, no fake 'Java impossible' claims."""
import copy
import gzip
import io
import json
import pathlib
import struct
import sys
import unittest
import zipfile

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from voxel_architect import (MAX_BLOCKS, DATA_VERSION, MODES, PALETTES,
                              generate_structure, preview_structure, serialize_structure)
from studio import create_project_files, hmod_zip, project_zip

D={'id':'test','name':'Test','author':'Author','blocks':[],'items':[],'recipes':[],
   'structures':[{'id':'maze','kind':'labyrinth','theme':'stone','size':19,'seed':1337}]}

# Small independent NBT binary reader for the exact structure schema; no roundtrip
# through the encoder itself, so it catches malformed tag headers and lists.
class NbtReader:
    def __init__(self,data):self.data=memoryview(data);self.p=0
    def read(self,n):
        out=self.data[self.p:self.p+n]
        if len(out)!=n:raise ValueError('Truncated NBT')
        self.p+=n;return out
    def unpack(self,fmt):return struct.unpack(fmt,self.read(struct.calcsize(fmt)))
    def string(self):
        (n,)=self.unpack('>H');return self.read(n).tobytes().decode('utf-8')
    def payload(self,kind):
        if kind==3:return self.unpack('>i')[0]
        if kind==8:return self.string()
        if kind==9:
            element,length=self.unpack('>BI')
            if length>20000:raise ValueError('Too many entries')
            return [self.payload(element) for _ in range(length)]
        if kind==10:
            members={}
            while True:
                (kind,)=self.unpack('>B')
                if kind==0:break
                key=self.string();members[key]=self.payload(kind)
            return members
        raise ValueError(f'Unsupported tag {kind}')
    def parse(self):
        (kind,)=self.unpack('>B');assert kind==10
        assert self.string()==''
        root=self.payload(kind)
        assert self.p==len(self.data), 'Trailing NBT bytes'
        return root

class Structures(unittest.TestCase):
    def test_patterns_are_nonempty_deterministic_and_bounded(self):
        for kind in MODES:
            for size in (7,19,29):
                spec={'id':'x','kind':kind,'size':size,'seed':42,'theme':'nether'}
                with self.subTest(kind=kind,size=size):
                    one=generate_structure(spec);two=generate_structure(spec)
                    self.assertEqual(one,two)
                    self.assertLessEqual(len(one),MAX_BLOCKS)
                    self.assertTrue(all(0<=v<32 for pos in one for v in pos))
                    self.assertEqual(set(one.values())-set(PALETTES['nether']),set())
    def test_seed_changes_maze_not_its_dimensions(self):
        def f(seed):return generate_structure({'id':'x','kind':'labyrinth','theme':'stone','size':19,'seed':seed})
        self.assertNotEqual(f(1),f(2))
        self.assertEqual(len(f(1)),len(f(2)))
    def test_nbt_is_valid_tree_with_palette_and_coordinates(self):
        spec={'id':'x','kind':'spiral_tower','size':19,'seed':1,'theme':'copper'}
        vox=generate_structure(spec)
        nbt=serialize_structure(vox)
        self.assertTrue(nbt.startswith(b'\x1f\x8b\x08'))
        root=NbtReader(gzip.decompress(nbt)).parse()
        self.assertEqual(root['DataVersion'],DATA_VERSION)
        self.assertEqual(root['size'],[max(k[i] for k in vox)+1 for i in range(3)])
        self.assertEqual(len(root['blocks']),len(vox))
        self.assertEqual(root['entities'],[])
        palette=[entry['Name'] for entry in root['palette']]
        self.assertEqual(set(palette),set(vox.values()))
        for entry in root['blocks']:
            self.assertEqual(vox[tuple(entry['pos'])],palette[entry['state']])
    def test_reproducible_bytes_for_every_theme(self):
        for theme in PALETTES:
            spec={'id':'x','kind':'sky_dome','size':23,'theme':theme,'seed':7}
            with self.subTest(theme=theme):
                first=serialize_structure(generate_structure(spec))
                second=serialize_structure(generate_structure(spec))
                self.assertEqual(first,second)
    def test_rejects_invalid_and_resource_exhausting_inputs(self):
        good={'id':'safe','kind':'labyrinth','theme':'stone','size':19,'seed':1}
        for changes in ({'id':'../attack'},{'kind':'invalid'},{'size':3},{'size':30},
                        {'size':9.5},{'size':True},{'seed':-1},{'seed':2**31},
                        {'seed':'1'},{'theme':'unknown'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                generate_structure({**good,**changes})
    def test_only_structure_mod_can_be_exported(self):
        name,files=create_project_files(D)
        self.assertIn('data/test/structure/maze.nbt',files)
        self.assertTrue(files['data/test/structure/maze.nbt'].startswith(b'\x1f\x8b'))
        self.assertIn('horizon-mod.toml',files)
        with zipfile.ZipFile(io.BytesIO(hmod_zip(D))) as mod:
            self.assertIsNone(mod.testzip())
            self.assertEqual(mod.read('data/test/structure/maze.nbt'),files['data/test/structure/maze.nbt'])
        with zipfile.ZipFile(io.BytesIO(project_zip(D))) as source:
            self.assertIn('test/data/test/structure/maze.nbt',source.namelist())
    def test_preview_matches_nbt(self):
        spec=D['structures'][0]
        info=preview_structure(spec,layer=0)
        self.assertEqual(len(info['voxels']),info['blocks'])
        self.assertEqual(info['top_down'].count('\n'),18)
        self.assertIn('█',info['top_down'])
        self.assertEqual(len(info['palette']),len(set(info['palette'])))
    def test_rejects_duplicate_or_oversized_structures(self):
        with self.assertRaisesRegex(ValueError,'Duplicate structure'):
            create_project_files({**D,'structures':D['structures']*2})
        with self.assertRaisesRegex(ValueError,'Maximum'):
            create_project_files({**D,'structures':D['structures']*9})
    def test_no_unverified_native_code_or_java_assets(self):
        _,files=create_project_files(D)
        self.assertFalse(any(x.endswith(('.wasm','.jar','.rs','.dll','.png')) for x in files))
        self.assertTrue(all(x.startswith(('data/','assets/')) or x=='horizon-mod.toml' for x in files))

if __name__=='__main__':unittest.main()
