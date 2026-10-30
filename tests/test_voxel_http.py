import http.client
import json
import pathlib
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from studio import Handler

class VoxelHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def post(self,payload):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=5)
        conn.request('POST','/api/structure-preview',json.dumps(payload),{'Content-Type':'application/json'})
        response=conn.getresponse();status=response.status;body=response.read();conn.close()
        return status,json.loads(body)
    def test_preview_route(self):
        status,data=self.post({'structure':{'id':'maze','kind':'labyrinth','theme':'nether','size':9,'seed':42},'layer':2})
        self.assertEqual(status,200)
        self.assertEqual(data['layer'],2)
        self.assertGreater(data['blocks'],100)
        self.assertEqual(len(data['voxels']),data['blocks'])
    def test_bad_preview_rejected(self):
        for obj in ({'structure':{'id':'../../bad','kind':'labyrinth','size':9,'seed':3}},
                    {'structure':{'id':'maze','kind':'labyrinth','size':9,'seed':3},'layer':32}):
            code,data=self.post(obj)
            self.assertEqual(code,400)
            self.assertIn('error',data)
if __name__=='__main__':unittest.main()
