"""Exercise production HTTP/session/CSRF and command-boundary behaviour offline."""
import http.client
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
from console import Backend, ConsoleServer, make_handler, password_hash, validate_action


class FakeBackend:
    def __init__(self):
        self.calls = []
    def snapshot(self):
        return {'stale': True, 'runtime': {}, 'cases': [], 'procedures': [], 'audit': [], 'advice': [], 'recipes': []}
    def action(self, data):
        validate_action(data)
        self.calls.append(data)
        return {'saved': True}


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.server = ConsoleServer(('127.0.0.1', 0), http.server.BaseHTTPRequestHandler)
        self.port = self.server.server_port
        salt = '00'*16
        self.server.RequestHandlerClass = make_handler({'salt': salt, 'hash': password_hash('test-only-password', salt)}, self.backend, self.port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = ''
        self.csrf = ''

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, data=None, extra=None):
        client = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        headers = {'Origin': f'http://127.0.0.1:{self.port}', 'Content-Type': 'application/json',
                   'Cookie': self.cookie, 'X-CSRF-Token': self.csrf}
        headers.update(extra or {})
        client.request('GET' if data is None else 'POST', path, None if data is None else json.dumps(data), headers)
        response = client.getresponse()
        result = (response.status, response.read(), dict(response.getheaders()))
        client.close()
        return result

    def login(self):
        status, body, headers = self.request('/api/login', {'password': 'test-only-password'})
        self.assertEqual(status, 200)
        self.cookie = headers['Set-Cookie'].split(';')[0]
        self.csrf = json.loads(body)['csrf']
        return headers

    def test_read_requires_authentication(self):
        self.assertEqual(self.request('/api/snapshot')[0], 401)

    def test_password_is_checked(self):
        self.assertEqual(self.request('/api/login', {'password': 'wrong'})[0], 401)

    def test_authenticated_snapshot_and_cookie_security(self):
        headers = self.login()
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', headers['Set-Cookie'])
        self.assertTrue(json.loads(self.request('/api/snapshot')[1])['stale'])

    def test_cross_origin_login_refused(self):
        self.assertEqual(self.request('/api/login', {'password': 'test-only-password'}, {'Origin': 'https://evil.invalid'})[0], 403)

    def test_dns_rebinding_host_refused(self):
        self.assertEqual(self.request('/', extra={'Host': 'evil.invalid'})[0], 403)

    def test_mutation_requires_csrf(self):
        self.login()
        self.csrf = 'wrong'
        self.assertEqual(self.request('/api/action', {'action': 'approve', 'id': 1, 'notes': 'Reviewed evidence'}, {})[0], 403)
        self.assertEqual(self.backend.calls, [])

    def test_approved_operation_passes_typed_boundary(self):
        self.login()
        self.assertEqual(self.request('/api/action', {'action': 'approve', 'id': 1, 'notes': 'Reviewed evidence'})[0], 200)
        self.assertEqual(len(self.backend.calls), 1)

    def test_arbitrary_command_not_exposed(self):
        self.login()
        self.assertEqual(self.request('/api/action', {'action': 'shell', 'command': 'rm -rf /'})[0], 400)
        self.assertEqual(self.backend.calls, [])

    def test_logout_invalidates_session(self):
        self.login()
        self.assertEqual(self.request('/api/logout', {})[0], 200)
        self.assertEqual(self.request('/api/snapshot')[0], 401)

    def test_login_throttled(self):
        for _ in range(5):
            self.assertEqual(self.request('/api/login', {'password': 'wrong'})[0], 401)
        self.assertEqual(self.request('/api/login', {'password': 'wrong'})[0], 429)

    def test_unexpected_fields_and_boolean_id_refused(self):
        for change in ({'who': 'admin'}, {'id': True}, {'id': -1}, {'recipe': 'arbitrary'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_action({'action': 'approve', 'id': 1, 'notes': 'Reviewed evidence', **change})

    def test_shell_characters_remain_literal_argv(self):
        args = validate_action({'action': 'investigate', 'id': 1, 'cause': 'bad_endpoint', 'recipe': 'job_config', 'notes': 'Evidence; $(touch /tmp/no) `not executed`'})
        self.assertEqual(args[args.index('--notes')+1], 'Evidence; $(touch /tmp/no) `not executed`')
        self.assertEqual(args[args.index('--who')+1], 'console-operator')

    def test_stale_backend_never_starts_approval_process(self):
        backend = Backend()
        with patch.object(backend, 'snapshot', return_value={'stale': True}), patch('console.subprocess.run') as run:
            with self.assertRaises(ValueError):
                backend.action({'action': 'approve', 'id': 1, 'notes': 'Reviewed evidence'})
            run.assert_not_called()

    def test_statement_submit_requires_csrf(self):
        self.login();self.csrf='wrong'
        self.assertEqual(self.request('/api/statements',{'idempotency_key':'00000000-0000-0000-0000-000000000001'})[0],403)

    def test_statement_read_requires_authentication(self):
        self.assertEqual(self.request('/api/statements')[0],401)

    def test_static_assets_and_csp(self):
        status, body, headers = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn(b'MAPE-K', body)
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertEqual(self.request('/../../.config/healer-console/auth.json')[0], 401)


if __name__ == '__main__':
    unittest.main()
