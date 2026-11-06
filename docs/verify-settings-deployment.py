from pathlib import Path
from urllib.request import urlopen
import re
import hashlib

root = Path('/srv/trace-tutor/frontend/dist')
base = 'https://trace.musfiqurtuhin.me'
with urlopen(base + '/profile', timeout=30) as response:
    html = response.read()
    assert response.status == 200
assert html == (root / 'index.html').read_bytes(), 'Live HTML differs from deployed build'
assets = set(re.findall(r'/assets/[^"\s<>]+', html.decode()))
assets.add('/assets/Profile-Bl7RKYRH.js')
for asset in sorted(assets):
    with urlopen(base + asset, timeout=30) as response:
        body = response.read()
        assert response.status == 200
    assert body == (root / asset.lstrip('/')).read_bytes(), asset
    print('HTTP 200; build hash matched:', asset, hashlib.sha256(body).hexdigest()[:16])
js = b'\n'.join(p.read_bytes() for p in (root / 'assets').glob('index-*.js'))
assert b'fixed inset-0 overflow-hidden bg-surface text-on-surface flex' in js
assert b'overscroll-contain' in js
assert b'max-w-5xl mx-auto w-full shrink-0 space-y-5 pb-10' in (root / 'assets/Profile-Bl7RKYRH.js').read_bytes()
print('PASS: public profile page serves the deployed settings layout fix.')
