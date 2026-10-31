"""Security tests for loopback API, CSRF, DNS rebinding and content types."""
import http.client
import json
from pathlib import Path
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studio import Handler
from security.request_policy import session_token


class ApiSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=5)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        status, result_headers, raw = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return status, result_headers, raw

    def post(self, headers=None):
        default = {'Content-Type': 'application/json', 'X-Studio-Token': session_token(self.server)}
        default.update(headers or {})
        return self.request('POST', '/api/preview', body=b'{}', headers=default)

    def test_pages_may_run_only_scripts_from_the_studio_origin(self):
        # S3/CSP: no inline <script>, no inline event handler, no eval; the policy says so too.
        import re
        status, headers, page = self.request('GET', '/', headers={'Host': f"127.0.0.1:{self.server.server_address[1]}"})
        self.assertEqual(status, 200)
        policy = dict(part.strip().split(' ', 1) for part in headers['Content-Security-Policy'].split(';') if part.strip())
        self.assertEqual(policy['script-src'], "'self'")
        for directive, value in (('object-src', "'none'"), ('base-uri', "'none'"), ('frame-ancestors', "'none'")):
            self.assertEqual(policy[directive], value)
        self.assertEqual(policy['connect-src'], "'self'")
        import studio
        desktop = dict(part.strip().split(' ', 1) for part in studio.content_security_policy(True).split(';'))
        self.assertEqual(desktop['connect-src'], "'self' ipc: http://ipc.localhost", 'the shell IPC, and only for connections')
        self.assertEqual({k: v for k, v in desktop.items() if k != 'connect-src'},
                         {k: v for k, v in policy.items() if k != 'connect-src'})
        html = page.decode('utf-8')
        self.assertEqual(re.findall(r'<script(?![^>]*\bsrc=)[^>]*>', html), [], 'inline scripts')
        self.assertEqual(re.findall(r'\son[a-z]+\s*=', html), [], 'inline event handlers')
        root = Path(__file__).resolve().parents[1]
        import studio
        for name in studio.WEB_SCRIPTS:
            source = (root / name).read_text(encoding='utf-8')
            self.assertIsNone(re.search(r'\beval\(|new Function\(|setTimeout\([\'"`]', source), name)

    def test_session_endpoint_is_not_cacheable(self):
        status, headers, data = self.request('GET', '/api/session')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["token"], session_token(self.server))
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_missing_and_invalid_tokens_are_rejected(self):
        for token in ('', 'incorrect', 'A' * 300):
            with self.subTest(token=token):
                code, _, data = self.post({'X-Studio-Token': token})
                self.assertEqual(code, 403)
                self.assertIn(b"token", data)

    def test_correct_token_reaches_application_validator(self):
        code, _, data = self.post()
        self.assertEqual(code, 400)
        self.assertIn(b"error", data)

    def test_cross_origin_requests_are_rejected_even_with_token(self):
        port = self.server.server_address[1]
        for bad_origin in ("null", "http://attacker.example", f"http://localhost:{port + 1}", "https://127.0.0.1:" + str(port)):
            with self.subTest(origin=bad_origin):
                code, _, _ = self.post({'Origin': bad_origin})
                self.assertEqual(code, 403)

    def test_cross_site_fetch_metadata_is_rejected(self):
        for site in ('same-site', 'cross-site'):
            with self.subTest(site=site):
                code, _, _ = self.post({'Sec-Fetch-Site': site})
                self.assertEqual(code, 403)

    def test_dns_rebinding_host_rejected_on_get_and_post(self):
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                headers = {'Host': 'attacker.example:' + str(self.server.server_address[1])}
                if method == 'POST':
                    headers.update({'X-Studio-Token': session_token(self.server), 'Content-Type': 'application/json'})
                code, _, data = self.request(method, '/api/session' if method == 'GET' else '/api/preview', b'{}' if method == 'POST' else None, headers)
                self.assertEqual(code, 403)

    def test_wrong_content_type_rejected(self):
        code, _, _ = self.post({'Content-Type': 'text/plain'})
        self.assertEqual(code, 415)

    def test_pack_requires_octet_stream(self):
        headers = {'Content-Type': 'application/json', 'X-Studio-Token': session_token(self.server)}
        code, _, _ = self.request('POST', '/api/resourcepack', b'garbage', headers)
        self.assertEqual(code, 415)

    def test_separate_servers_get_independent_secrets(self):
        another = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        try:
            self.assertNotEqual(session_token(self.server), session_token(another))
        finally:
            another.server_close()


if __name__ == '__main__':
    unittest.main()
