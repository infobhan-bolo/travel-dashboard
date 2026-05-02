#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json
import subprocess
import os
from datetime import datetime
import threading

BASE = Path('/Users/bolo/.openclaw/workspace/travel-dashboard')
REFRESH_CMD = ['/Applications/Xcode.app/Contents/Developer/usr/bin/python3', str(BASE / 'extract_travel_caldav.py')]
REFRESH_LOG = BASE / 'refresh-debug.log'
_refresh_lock = threading.Lock()
_refresh_state = {
    'running': False,
    'started_at': None,
    'finished_at': None,
    'last_returncode': None,
    'last_stdout': '',
    'last_stderr': '',
}


def run_refresh_worker():
    with _refresh_lock:
        if _refresh_state['running']:
            return False
        _refresh_state['running'] = True
        _refresh_state['started_at'] = datetime.now().isoformat()
        _refresh_state['finished_at'] = None

    try:
        p = subprocess.run(REFRESH_CMD, cwd=str(BASE), capture_output=True, text=True, timeout=240)
        with open(REFRESH_LOG, 'a') as f:
            f.write(f"[{_refresh_state['started_at']}] rc={p.returncode}\n")
            if p.stdout:
                f.write('STDOUT:\n' + p.stdout + '\n')
            if p.stderr:
                f.write('STDERR:\n' + p.stderr + '\n')
            f.write('---\n')
        _refresh_state['last_returncode'] = p.returncode
        _refresh_state['last_stdout'] = p.stdout[-4000:] if p.stdout else ''
        _refresh_state['last_stderr'] = p.stderr[-4000:] if p.stderr else ''
    except Exception as e:
        with open(REFRESH_LOG, 'a') as f:
            f.write(f"[{_refresh_state['started_at']}] exception={e}\n---\n")
        _refresh_state['last_returncode'] = -1
        _refresh_state['last_stdout'] = ''
        _refresh_state['last_stderr'] = str(e)
    finally:
        _refresh_state['running'] = False
        _refresh_state['finished_at'] = datetime.now().isoformat()
    return True


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/__refresh__'):
            started = False
            if not _refresh_state['running']:
                threading.Thread(target=run_refresh_worker, daemon=True).start()
                started = True
            self.send_response(202)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'status': 'refresh-started' if started else 'refresh-already-running',
                'state': _refresh_state,
            }).encode())
            return
        if self.path.startswith('/__refresh_status__'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(_refresh_state).encode())
            return
        return super().do_GET()

if __name__ == '__main__':
    os.chdir(BASE)
    server = ThreadingHTTPServer(('0.0.0.0', 8767), Handler)
    server.serve_forever()
