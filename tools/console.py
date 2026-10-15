"""Loopback-only operator console. Use an SSH tunnel; never publish this port.

No shell endpoint: mutations use the existing reviewed operator CLI. Passwords
are set interactively and only a salted scrypt hash is stored outside the repo.
"""
import argparse
import getpass
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH = Path.home() / '.config/healer-console/auth.json'
RECIPES = {'job_config', 'job_workers', 'job_database', 'job_network', 'job_template', 'job_compute'}


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def validate_action(data):
    """Produce an argv list, never executable operator-supplied commands."""
    action = data.get('action')
    if action not in {'investigate', 'approve', 'reject', 'record-human', 'promote'}:
        raise ValueError('Unsupported operation')
    identifier = data.get('id')
    if type(identifier) is not int or not 1 <= identifier <= 2**31-1:
        raise ValueError('A positive incident or procedure id is required')
    permitted = {'action', 'id', 'notes'}
    args = [action, str(identifier), '--who', 'console-operator']
    if action != 'promote':
        notes = data.get('notes')
        if not isinstance(notes, str) or not 8 <= len(notes.strip()) <= 2000:
            raise ValueError('Explain the evidence and decision in 8–2000 characters')
        args += ['--notes', notes.strip()]
    if action in {'investigate', 'record-human'}:
        permitted.add('recipe')
        if data.get('recipe') not in RECIPES:
            raise ValueError('Choose a reviewed recipe')
        args += ['--recipe', data['recipe']]
    if action == 'investigate':
        permitted.add('cause')
        import re
        if not isinstance(data.get('cause'), str) or not re.fullmatch('[a-z][a-z0-9_]{2,80}', data['cause']) or data['cause'] == 'unknown':
            raise ValueError('Provide a specific cause identifier')
        args += ['--cause', data['cause']]
    if set(data) - permitted:
        raise ValueError('Unexpected fields')
    return args


class Backend:
    def __init__(self):
        self.lock = threading.Lock()

    def snapshot(self):
        result = {'application': 'Kubernetes job-processing service', 'deadline_seconds': 30,
                  'recipes': sorted(RECIPES), 'cases': [], 'procedures': [], 'audit': []}
        try:
            with urllib.request.urlopen('http://10.1.1.205:9109/status', timeout=3) as response:
                result['runtime'] = json.load(response)
            stamp = result['runtime'].get('time', 0)
            result['stale'] = time.time() - stamp > 45
        except (OSError, ValueError):
            result['stale'] = True
            result['runtime'] = {}
        db_path = ROOT / 'state/jobs/operator.db'
        if db_path.exists():
            with sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True, timeout=3) as db:
                db.row_factory = sqlite3.Row
                for name, table, order in [('cases', 'cases', 'id DESC'), ('procedures', 'procedures', 'id DESC'), ('audit', 'operator_audit', 'id DESC')]:
                    result[name] = [dict(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY {order} LIMIT 100')]
        knowledge_path = ROOT / 'state/jobs/knowledge.db'
        result['advice'] = []
        if knowledge_path.exists():
            with sqlite3.connect(knowledge_path.as_uri() + '?mode=ro', uri=True, timeout=3) as db:
                db.row_factory = sqlite3.Row
                result['advice'] = [dict(row) for row in db.execute('SELECT * FROM advice ORDER BY id DESC LIMIT 20')]
        return result

    def action(self, data):
        args = validate_action(data)
        if self.snapshot()['stale'] and data['action'] != 'reject':
            raise ValueError('Controller evidence is stale; restore monitoring before approving an operation')
        if not self.lock.acquire(blocking=False):
            raise ValueError('Another operator operation is still running')
        try:
            # Existing CLI retains ownership, freshness, recipe and verifier guards.
            result = subprocess.run([sys.executable, str(ROOT/'tools/jobs.py'), *args],
                                    cwd=ROOT, capture_output=True, text=True, timeout=240)
            if result.returncode:
                # Do not expose a subprocess traceback or any environment values.
                raise ValueError('Operation refused or verification failed. Review the incident and local service logs.')
            return json.loads(result.stdout)
        finally:
            self.lock.release()


class ConsoleServer(ThreadingHTTPServer):
    daemon_threads = True


def make_handler(auth, backend, port):
    sessions = {}
    attempts = []
    lock = threading.Lock()
    origin = f'http://127.0.0.1:{port}'
    expected_host = f'127.0.0.1:{port}'

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def reply(self, code, value, kind='application/json', cookie=None):
            body = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(code)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if cookie:
                self.send_header('Set-Cookie', cookie)
            self.end_headers()
            self.wfile.write(body)

        def session(self):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get('Cookie', ''))
                key = cookie['healer_session'].value
            except (KeyError, ValueError, CookieError):
                return None
            with lock:
                now = time.time()
                for token in list(sessions):
                    if sessions[token]['expires'] <= now:
                        del sessions[token]
                return sessions.get(key)

        def body(self):
            if self.headers.get('Transfer-Encoding') or self.headers.get_content_type() != 'application/json':
                raise ValueError('JSON with Content-Length is required')
            size = int(self.headers.get('Content-Length', '0'))
            if not 1 <= size <= 8192:
                raise ValueError('Invalid body size')
            value = json.loads(self.rfile.read(size))
            if not isinstance(value, dict):
                raise ValueError('Expected an object')
            return value

        def do_GET(self):
            if self.headers.get('Host') != expected_host:
                return self.reply(403, {'error': 'Use the documented loopback address'})
            assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/console.js': ('console.js', 'application/javascript'),
                      '/console.css': ('console.css', 'text/css')}
            if self.path in assets:
                filename, kind = assets[self.path]
                return self.reply(200, (ROOT/'web'/filename).read_bytes(), kind)
            session = self.session()
            if not session:
                return self.reply(401, {'error': 'Sign in to view the lab'})
            if self.path == '/api/session':
                return self.reply(200, {'csrf': session['csrf'], 'operator': 'console-operator'})
            if self.path == '/api/snapshot':
                try:
                    return self.reply(200, backend.snapshot())
                except (OSError, ValueError, sqlite3.Error):
                    return self.reply(503, {'error': 'Evidence is temporarily unreadable'})
            return self.reply(404, {'error': 'Not found'})

        def do_POST(self):
            # Exact Host also prevents DNS rebinding; Origin is mandatory even for login.
            if self.headers.get('Host') != expected_host or self.headers.get('Origin') != origin:
                return self.reply(403, {'error': 'Origin refused'})
            try:
                data = self.body()
                if self.path == '/api/login':
                    with lock:
                        now = time.time()
                        attempts[:] = [stamp for stamp in attempts if now-stamp < 60]
                        if len(attempts) >= 5:
                            return self.reply(429, {'error': 'Wait one minute before another sign-in attempt'})
                        attempts.append(now)
                    password = data.get('password')
                    if not isinstance(password, str) or len(password) > 1024 or not hmac.compare_digest(password_hash(password, auth['salt']), auth['hash']):
                        return self.reply(401, {'error': 'Sign-in failed'})
                    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                    with lock:
                        # One operator session; a new login invalidates the previous one.
                        sessions.clear()
                        sessions[token] = {'expires': time.time()+3600, 'csrf': csrf}
                    return self.reply(200, {'csrf': csrf}, cookie=f'healer_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600')
                session = self.session()
                if not session:
                    return self.reply(401, {'error': 'Session expired'})
                if not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), session['csrf']):
                    return self.reply(403, {'error': 'CSRF token refused'})
                if self.path == '/api/logout':
                    with lock:
                        sessions.clear()
                    return self.reply(200, {'signed_out': True}, cookie='healer_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
                if self.path == '/api/action':
                    return self.reply(200, backend.action(data))
                return self.reply(404, {'error': 'Not found'})
            except (ValueError, UnicodeError, TypeError):
                return self.reply(400, {'error': 'Invalid request or operation refused. Check the entered fields and current incident.'})
            except (OSError, subprocess.TimeoutExpired):
                return self.reply(503, {'error': 'Operation unavailable or timed out; inspect the incident before retrying'})

        def log_message(self, *args):
            pass  # Passwords, notes and tokens never enter access logs.
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--set-password', action='store_true')
    parser.add_argument('--port', type=int, default=8085)
    args = parser.parse_args()
    if args.set_password:
        password = getpass.getpass('New console password (at least 14 characters): ')
        if len(password) < 14 or password != getpass.getpass('Repeat password: '):
            raise SystemExit('Password too short or confirmation differs')
        salt = secrets.token_hex(16)
        AUTH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(AUTH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as file:
            json.dump({'salt': salt, 'hash': password_hash(password, salt)}, file)
        os.chmod(AUTH, 0o600)
        print('Console password hash saved outside the repository.')
        return
    if not 1024 <= args.port <= 65535:
        parser.error('Use an unprivileged port')
    if not AUTH.exists():
        raise SystemExit('Run with --set-password first.')
    auth = json.loads(AUTH.read_text())
    server = ConsoleServer(('127.0.0.1', args.port), make_handler(auth, Backend(), args.port))
    print(f'Operator console: http://127.0.0.1:{args.port} (SSH tunnel required)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
