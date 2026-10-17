"""Owned bounded upstream test instrument for the real HAProxy gateway.

Only nonce echo and a capped hold are supported. No banking/business operations.
"""
import json
import re
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

SOCKET='/run/platform-healer/gateway/upstream.sock'
slots=threading.BoundedSemaphore(100)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query=urlsplit(self.path);values=parse_qs(query.query)
        nonce=values.get('nonce',[''])[0]
        if query.path not in ('/transaction','/hold') or not re.fullmatch('[a-f0-9]{16,64}',nonce):
            self.send_error(400);return
        try:hold=float(values.get('seconds',['0'])[0]) if query.path=='/hold' else 0
        except ValueError:self.send_error(400);return
        if not 0<=hold<=45 or not slots.acquire(blocking=False):self.send_error(429);return
        try:
            if hold:time.sleep(hold)
            raw=('gateway-ok:'+nonce+'\n').encode()
            self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.send_header('Connection','close');self.end_headers();self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):pass
        finally:slots.release()
    def log_message(self,*args):pass


class UnixHTTP(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True


def main():
    path=Path(SOCKET);path.unlink(missing_ok=True)
    unix=UnixHTTP(SOCKET,Handler)
    path.chmod(0o660)
    threading.Thread(target=unix.serve_forever,daemon=True).start()
    ThreadingHTTPServer(('127.0.0.1',19080),Handler).serve_forever()


if __name__=='__main__':main()
