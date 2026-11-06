"""Verify the public profile bundle and responsive CSS without data writes."""
from pathlib import Path
import json
from urllib.request import Request, urlopen

result = json.loads((Path(__file__).parent / 'PUBLISHED.json').read_text())
origin = 'https://trace.musfiqurtuhin.me'

def get(path):
    with urlopen(Request(origin + path, headers={'Cache-Control': 'no-cache'}), timeout=25) as response:
        assert response.status == 200
        return response.read().decode(), response.headers.get('Content-Type', '')

assets = result['verified_assets']
entry = next(p for p in assets if p.startswith('assets/index-') and p.endswith('.js'))
css_path = next(p for p in assets if p.endswith('.css'))
profile_path = next(p for p in assets if p.startswith('assets/Profile-'))
html, mime = get('/profile?verify-profile-header=20261026')
assert 'text/html' in mime and '/' + entry in html and '/' + css_path in html
entry_code, _ = get('/' + entry)
assert profile_path.removeprefix('assets/') in entry_code
profile, mime = get('/' + profile_path)
assert 'javascript' in mime
assert 'grid-cols-[auto_minmax(0,1fr)]' in profile
assert 'col-span-2 xl:col-span-1' in profile
assert '[overflow-wrap:anywhere]' in profile
css, mime = get('/' + css_path)
assert 'text/css' in mime
assert 'grid-template-columns:auto minmax(0,1fr)' in css and 'overflow-wrap:anywhere' in css
health, _ = get('/api/health/')
assert json.loads(health)['database'] == 'ok'
print(json.dumps({'profile_chunk': profile_path, 'responsive_css': css_path, 'updated_header_served': True, 'database_health': 'ok'}, indent=2))
