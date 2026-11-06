"""Package only the four expert-portal runtime fixes and staging-only tests."""
from pathlib import Path
import hashlib
import json
import tarfile

here = Path(__file__).resolve().parent
root = here.parents[1]
baseline = json.loads((here / 'baseline/baseline-hashes.json').read_text())
runtime = [
    'src/pages/ExpertPortal.jsx',
    'src/components/Layout/AppShell.jsx',
    'src/services/assessmentTiming.js',
    'src/services/expertText.js',
]
manifest = {rel: {'before': baseline.get(rel), 'after': hashlib.sha256((root / 'frontend' / rel).read_bytes()).hexdigest()} for rel in runtime}
(here / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n')
with tarfile.open(here / 'release.tar.gz', 'w:gz') as archive:
    archive.add(here / 'release.json', arcname='release.json')
    archive.add(here / 'baseline/baseline-hashes.json', arcname='baseline-hashes.json')
    for rel in runtime:
        archive.add(root / 'frontend' / rel, arcname='runtime/' + rel)
    for name in ('expert-portal.test.jsx', 'app-shell-navigation.test.jsx', 'assessment-timing.test.mjs'):
        archive.add(root / 'frontend/tests' / name, arcname='validation-tests/' + name)
print('Prepared four runtime files; package manifests and unrelated local changes excluded.')
