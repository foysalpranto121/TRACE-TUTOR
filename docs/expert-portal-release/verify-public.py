"""Independent public HTTP verification; no authentication or data writes."""
from pathlib import Path
import json
from urllib.request import Request, urlopen

release = json.loads((Path(__file__).parent / 'PUBLISHED.json').read_text())
origin = 'https://trace.musfiqurtuhin.me'

def get(path):
    with urlopen(Request(origin + path, headers={'Cache-Control': 'no-cache'}), timeout=25) as response:
        assert response.status == 200
        return response.read().decode(), response.headers.get('Content-Type', '')

html, content_type = get('/expert?verify-expert-fixes=20261026')
assert 'text/html' in content_type
entry = next(path for path in release['verified_assets'] if path.startswith('assets/index-') and path.endswith('.js'))
expert = next(path for path in release['verified_assets'] if path.startswith('assets/ExpertPortal-'))
assert '/' + entry in html
javascript, content_type = get('/' + entry)
assert 'javascript' in content_type and expert.removeprefix('assets/') in javascript
portal, content_type = get('/' + expert)
assert 'javascript' in content_type
assert 'Unsaved draft · kept while this portal is open. Save before leaving or refreshing.' in portal
assert 'grade_revision' in portal and 'onChange' in portal
health, _ = get('/api/health/')
assert json.loads(health)['database'] == 'ok'
print(json.dumps({'public_index': entry, 'expert_chunk': expert, 'grade_draft_code_served': True, 'database_health': 'ok'}, indent=2))
