#!/usr/bin/env python
"""
Tiny localhost-only receiver: the built-in browser pane can fetch files but not save
them, so a page script POSTs the bytes it fetched here, and they are written to
OUTDIR/<name> (name from the X-Name header, sanitised). Binds 127.0.0.1 only.
Writes <name>.json next to each file with bytes and sha256.
"""
import hashlib
import http.server
import json
import os
import re
import sys

OUTDIR = sys.argv[1]
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
os.makedirs(OUTDIR, exist_ok=True)


class H(http.server.BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Private-Network', 'true')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(self.path).query)
        raw = q.get('name', [self.headers.get('X-Name', 'file.bin')])[0]
        name = re.sub(r'[^A-Za-z0-9._,()+-]', '_', raw)[:200]
        n = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(n)
        p = os.path.join(OUTDIR, name)
        open(p, 'wb').write(data)
        meta = {'name': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                'source_url': self.headers.get('X-Source', '')}
        json.dump(meta, open(p + '.json', 'w'), indent=1)
        self.send_response(200)
        self._cors()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(meta).encode())
        print('saved', meta, flush=True)

    def log_message(self, *a):
        pass


http.server.ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
