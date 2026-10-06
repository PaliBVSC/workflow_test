"""Serve the Fin Facade Generator and bridge its "Build in Archicad" button to Archicad.

    python serve.py [--port 8000] [--allow-origin https://your-app.vercel.app]

Open http://localhost:8000. The page posts its elements to /api/build and this server
creates them in the running Archicad through Tapir (see archicad/build_facade.py).
Archicad's own API sends no CORS headers, so the browser cannot talk to it directly.

Only pages from localhost / 127.0.0.1 may call the API. To use the button from a
deployed copy of the page (e.g. on Vercel), pass that site's origin with --allow-origin.
"""
import argparse
import json
import os
import sys
import threading
import urllib.error
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, 'archicad'))
import build_facade  # noqa: E402

build_lock = threading.Lock()
allowed_origins = set()


def origin_allowed(origin):
    if not origin:
        return True
    host = urlparse(origin).hostname
    return host in ('localhost', '127.0.0.1') or origin in allowed_origins


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        if self.path.startswith('/api/'):
            super().log_message(fmt, *args)

    def send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        origin = self.headers.get('Origin')
        if origin and origin_allowed(origin):
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        origin = self.headers.get('Origin')
        if not self.path.startswith('/api/') or not origin_allowed(origin):
            self.send_response(403); self.end_headers(); return
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', origin)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Vary', 'Origin')
        self.end_headers()

    def do_GET(self):
        if self.path == '/api/status':
            if not origin_allowed(self.headers.get('Origin')):
                return self.send_json(403, {'ok': False, 'error': 'Origin not allowed'})
            try:
                ver = build_facade.tapir('GetAddOnVersion')['version']
                return self.send_json(200, {'ok': True, 'tapir': ver, 'port': build_facade.PORT})
            except urllib.error.URLError:
                return self.send_json(200, {'ok': False, 'error': f'Archicad is not answering on port {build_facade.PORT}. Open a project in Archicad with Tapir loaded.'})
            except Exception as e:
                return self.send_json(200, {'ok': False, 'error': str(e)})
        return super().do_GET()

    def do_POST(self):
        if self.path != '/api/build':
            return self.send_json(404, {'ok': False, 'error': 'Unknown endpoint'})
        if not origin_allowed(self.headers.get('Origin')):
            return self.send_json(403, {'ok': False, 'error': 'Origin not allowed. Start serve.py with --allow-origin for this site.'})
        try:
            data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
            model = {'fins': data['fins'], 'horizontals': data['horizontals']}
            origin = [float(v) for v in data.get('origin', [0, 0])]
            keep = bool(data.get('keep', False))
        except Exception as e:
            return self.send_json(400, {'ok': False, 'error': f'Bad request: {e}'})
        if not build_lock.acquire(blocking=False):
            return self.send_json(409, {'ok': False, 'error': 'A build is already running. Wait for it to finish.'})
        try:
            log = []
            result = build_facade.build(model, origin, keep, log=lambda m: (log.append(m), print(m)))
            if data.get('settings'):
                with open(os.path.join(ROOT, 'archicad', 'fin-facade.json'), 'w', encoding='utf8') as f:
                    json.dump(data['settings'], f, indent=1)
            return self.send_json(200, {'ok': True, **result, 'log': log})
        except urllib.error.URLError:
            return self.send_json(502, {'ok': False, 'error': f'Archicad is not answering on port {build_facade.PORT}.'})
        except Exception as e:
            return self.send_json(500, {'ok': False, 'error': str(e)})
        finally:
            build_lock.release()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--allow-origin', action='append', default=[])
    args = ap.parse_args()
    allowed_origins.update(o.rstrip('/') for o in args.allow_origin)
    srv = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Fin Facade Generator: http://localhost:{args.port}  (Ctrl+C to stop)')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
