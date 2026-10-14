#!/usr/bin/env python3
"""Synthetic infrastructure transaction: DNS -> Redis write -> local checkpoint.

This is a test workload, not a business application. Every request overwrites
one expiring Redis key and one small checkpoint, so the workload is bounded.
"""
import json
import os
import socket
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DNS = ('10.1.1.61', 1053)
EXPECTED = '10.1.1.61'
SPOOL = '/var/lib/healer-stack/checkpoint'
SPOOL_LOCK = threading.Lock()


def resolve():
    ident = os.urandom(2)
    labels = b''.join(bytes([len(x)]) + x.encode() for x in 'cache.lab.test'.split('.'))
    query = ident + struct.pack('!HHHHH', 0x100, 1, 0, 0, 0) + labels + b'\0' + struct.pack('!HH', 1, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(1)
        sock.connect(DNS)
        sock.send(query)
        data = sock.recv(2048)
    if data[:2] != ident or len(data) < 16 or data[3] & 15 or data[6:8] == b'\0\0':
        raise ValueError('DNS response has no valid answer')
    # This lab controls its sole A record. No general DNS parser is claimed.
    return socket.inet_ntoa(data[-4:])


def redis_command(host, *words):
    packet = f'*{len(words)}\r\n'.encode()
    for word in words:
        part = str(word).encode()
        packet += f'${len(part)}\r\n'.encode() + part + b'\r\n'
    with socket.create_connection((host, 6380), timeout=1) as sock:
        with open('/etc/healer-stack/cache-client.json') as handle:
            credentials = json.load(handle)
        auth = [b'AUTH', credentials['username'].encode(), credentials['password'].encode()]
        auth_packet = b'*3\r\n' + b''.join(f'${len(p)}\r\n'.encode()+p+b'\r\n' for p in auth)
        sock.sendall(auth_packet)
        if sock.recv(4096).strip() != b'+OK':
            raise ValueError('Redis authentication failed')
        sock.sendall(packet)
        reply = sock.recv(4096).decode(errors='replace').strip()
    if not reply or reply.startswith('-'):
        raise ValueError(reply or 'empty Redis reply')
    return reply


def transaction():
    started = time.monotonic()
    checks, evidence = {}, {}
    try:
        address = resolve()
        checks['dns_record'] = address == EXPECTED
        evidence['dns_record'] = address
    except (OSError, ValueError) as error:
        checks['dns_record'] = False
        evidence['dns_record'] = str(error)
    # Never follow an incorrect DNS answer to an unapproved target.
    if checks['dns_record']:
        try:
            redis_command(EXPECTED, 'SET', 'healer:transaction', 'ok', 'EX', 60)
            checks['cache_write'] = redis_command(EXPECTED, 'GET', 'healer:transaction').endswith('\r\nok')
            evidence['cache_write'] = 'SET and GET on expiring canary key'
        except (OSError, ValueError) as error:
            checks['cache_write'] = False
            evidence['cache_write'] = str(error)
    else:
        checks['cache_write'] = None  # dependency prevents measurement
        evidence['cache_write'] = 'not attempted: DNS contract failed'
    try:
        # Concurrent probes must not read another probe's truncated checkpoint.
        # This lock is process-local: the lab has one transaction service.
        with SPOOL_LOCK:
            with open(SPOOL, 'w') as handle:
                handle.write('ok\n')
            with open(SPOOL) as handle:
                checks['spool_write'] = handle.read() == 'ok\n'
        evidence['spool_write'] = SPOOL if checks['spool_write'] else SPOOL+': readback mismatch'
    except OSError as error:
        checks['spool_write'] = False
        evidence['spool_write'] = str(error)
    return {'healthy': all(v is True for v in checks.values()), 'checks': checks,
            'evidence': evidence, 'latency_ms': round((time.monotonic()-started)*1000, 3)}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/healthz':
            self.send_error(404); return
        result = transaction()
        payload = json.dumps(result).encode()
        self.send_response(200 if result['healthy'] else 503)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers(); self.wfile.write(payload)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    ThreadingHTTPServer(('10.1.1.60', 8088), Handler).serve_forever()
