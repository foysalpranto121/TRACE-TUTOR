"""Package only the profile header block; preserve other production copy."""
from pathlib import Path
import hashlib
import io
import json
import tarfile

here = Path(__file__).resolve().parent
root = here.parents[1]
rel = 'src/pages/Profile.jsx'
before = (here / 'baseline' / rel).read_bytes()
local = (root / 'frontend' / rel).read_bytes()
start = b'      {/* Header card */}'
end = b'      {notice && ('
assert before.count(start) == local.count(start) == 1
assert before.count(end) == local.count(end) == 1
new = before[:before.index(start)] + local[local.index(start):local.index(end)] + before[before.index(end):]
manifest = {rel: {'before': hashlib.sha256(before).hexdigest(), 'after': hashlib.sha256(new).hexdigest()}}
(here / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n')
with tarfile.open(here / 'release.tar.gz', 'w:gz') as archive:
    archive.add(here / 'release.json', arcname='release.json')
    archive.add(here / 'baseline/baseline-hashes.json', arcname='baseline-hashes.json')
    info = tarfile.TarInfo('runtime/' + rel)
    info.size = len(new)
    archive.addfile(info, io.BytesIO(new))
    for name in ('expert-portal.test.jsx', 'app-shell-navigation.test.jsx', 'assessment-timing.test.mjs'):
        archive.add(root / 'frontend/tests' / name, arcname='validation-tests/' + name)
print('Packaged profile header block only; all other production code and copy retained.')
