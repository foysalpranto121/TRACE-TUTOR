from pathlib import Path
from urllib.request import urlopen
import re

root = Path('/srv/trace-tutor/frontend/dist')
base = 'https://trace.musfiqurtuhin.me'
with urlopen(base + '/assessment', timeout=30) as response:
    html = response.read()
    assert response.status == 200
assert html == (root / 'index.html').read_bytes()
assets = set(re.findall(r'/assets/[^"\s<>]+', html.decode()))
assets.add('/assets/AssessmentPage-DWwVb-kk.js')
for asset in sorted(assets):
    with urlopen(base + asset, timeout=30) as response:
        body = response.read()
        assert response.status == 200
    assert body == (root / asset.lstrip('/')).read_bytes(), asset
    print('HTTP 200; live build matched:', asset)
chunk = (root / 'assets/AssessmentPage-DWwVb-kk.js').read_text()
assert 'Could not refresh the next assessment step.' in chunk
assert 'Continue to ' in chunk
assert 'getAssessmentItems' in chunk
print('PASS: public site serves the assessment phase refresh and Continue button.')
