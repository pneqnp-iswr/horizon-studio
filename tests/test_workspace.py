"""HS-006: real filesystem crash recovery and localhost workspace endpoints."""
import hashlib
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from security.request_policy import session_token
from studio import Handler, ThreadingHTTPServer
from studio_core.migrate import to_editor_state, upgrade
from studio_core.workspace import (WorkspaceStore, WorkspaceNotFound,
                                   WorkspaceConflict, WorkspaceCorrupt)
from studio_core.project_schema import dumps
from studio_core.storage import atomic_write_bytes


def example():
    return upgrade(json.loads((ROOT / 'examples/ruby_demo.hstudio.json').read_text(encoding='utf-8')))


class WorkspaceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = WorkspaceStore(Path(self.temp.name))
        self.document = example()

    def tearDown(self):
        self.temp.cleanup()

    def test_new_and_existing_document_require_expected_revision(self):
        with self.assertRaises(WorkspaceNotFound):
            self.store.recover('ruby_demo')
        first = self.store.save(self.document, expected_revision=None)
        self.assertEqual(first['revision'], hashlib.sha256(dumps(self.document).encode()).hexdigest())
        self.assertEqual(self.store.recover('ruby_demo')['document'], self.document)
        with self.assertRaises(WorkspaceConflict):
            self.store.save(self.document, expected_revision=None)
        self.assertEqual(self.store.save(self.document, expected_revision=first['revision'])['revision'],
                         first['revision'])

    def test_undoable_previous_snapshot_and_corrupt_primary_recovery(self):
        first = self.store.save(self.document, expected_revision=None)
        edited = json.loads(json.dumps(self.document))
        edited['project']['name'] = 'Second title'
        saved = self.store.save(edited, expected_revision=first['revision'])
        primary, backup = self.store.paths('ruby_demo')
        self.assertEqual(backup.read_bytes(), dumps(self.document).encode('utf-8'))
        self.assertNotEqual(saved['revision'], first['revision'])
        primary.write_bytes(b'{corrupted')
        result = self.store.recover('ruby_demo')
        self.assertTrue(result['recovered_from_backup'])
        self.assertEqual(result['revision'], first['revision'])
        self.assertEqual(result['document'], self.document)
        final = self.store.save(edited, expected_revision=result['revision'])
        self.assertEqual(final['revision'], saved['revision'])
        self.assertFalse(self.store.recover('ruby_demo')['recovered_from_backup'])

    def test_fault_injected_replace_does_not_corrupt_previous_snapshot(self):
        first = self.store.save(self.document, expected_revision=None)
        edited = json.loads(json.dumps(self.document))
        edited['project']['name'] = 'Interrupt-me'
        with patch('studio_core.workspace.atomic_write_bytes', wraps=atomic_write_bytes) as writer:
            original = writer.side_effect
            calls = [0]
            def interrupted(*args):
                calls[0] += 1
                if calls[0] == 2:
                    raise OSError('simulated crash before replacing primary')
                return original(*args)
            writer.side_effect = interrupted
            with self.assertRaisesRegex(OSError, 'simulated crash'):
                self.store.save(edited, expected_revision=first['revision'])
        self.assertEqual(self.store.recover('ruby_demo')['document'], self.document)

    def test_rejects_corrupt_primary_and_backup_without_data_loss(self):
        self.store.save(self.document, expected_revision=None)
        primary, backup = self.store.paths('ruby_demo')
        primary.write_bytes(b'not JSON')
        backup.write_bytes(b'also wrong')
        with self.assertRaises(WorkspaceCorrupt):
            self.store.recover('ruby_demo')
        with self.assertRaises(WorkspaceCorrupt):
            self.store.save(self.document, expected_revision=None)
        self.assertEqual(primary.read_bytes(), b'not JSON')

    def test_storage_name_cannot_escape_workspace_folder(self):
        with self.assertRaisesRegex(ValueError, 'Invalid'):
            self.store.paths('../evil')
        with self.assertRaisesRegex(ValueError, 'Invalid'):
            self.store.paths('/tmp/foo')
        self.assertEqual(self.store.paths('ruby_demo')[0].parent, Path(self.temp.name))

    def test_rejects_stale_revision_after_another_write(self):
        first = self.store.save(self.document, expected_revision=None)
        changed = json.loads(json.dumps(self.document))
        changed['project']['name'] = 'Other tab'
        self.store.save(changed, expected_revision=first['revision'])
        with self.assertRaises(WorkspaceConflict):
            self.store.save(self.document, expected_revision=first['revision'])
        self.assertEqual(self.store.recover('ruby_demo')['document'], changed)

    def test_rejects_wrong_doc_id_in_disk_slot(self):
        self.store.save(self.document, expected_revision=None)
        primary, _ = self.store.paths('ruby_demo')
        changed = json.loads(json.dumps(self.document))
        changed['project']['id'] = 'another_project'
        primary.write_bytes(dumps(changed).encode())
        with self.assertRaises(WorkspaceCorrupt):
            self.store.recover('ruby_demo')


class WorkspaceHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.server.studio_workspaces = WorkspaceStore(Path(cls.tmp.name))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.tmp.cleanup()

    def request(self, path, body, token=True):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=5)
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-Studio-Token'] = session_token(self.server)
        connection.request('POST', path, json.dumps(body), headers)
        response = connection.getresponse()
        status, data = response.status, json.loads(response.read())
        connection.close()
        return status, data

    def test_save_recover_conflict_and_security(self):
        document = example()
        state = to_editor_state(document)
        status, _ = self.request('/api/workspace/write', {'state':state,'expected_revision':None}, token=False)
        self.assertEqual(status, 403)
        status, saved = self.request('/api/workspace/write', {'state':state,'expected_revision':None})
        self.assertEqual(status, 200)
        status, _ = self.request('/api/workspace/write', {'state':state,'expected_revision':None})
        self.assertEqual(status, 409)
        status, result = self.request('/api/workspace/recover', {'project_id':'ruby_demo'})
        self.assertEqual(status, 200)
        self.assertEqual(result['revision'], saved['revision'])
        self.assertEqual(result['state'], state)
        status, _ = self.request('/api/workspace/recover', {'project_id':'../evil'})
        self.assertEqual(status, 400)


if __name__ == '__main__':
    unittest.main()
