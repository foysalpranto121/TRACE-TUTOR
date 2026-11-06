"""Build one explicit runtime release and verify all unchanged dependencies."""
from pathlib import Path
import base64, hashlib, json, tarfile
here = Path(__file__).resolve().parent
candidate = here / 'candidate'
audit = json.loads((here / 'server-source.json').read_text(encoding='utf-16'))
manifest = json.loads((here / 'candidate-manifest.json').read_text())
runtime = [
 'backend/assessment/views.py', 'backend/assessment/management/commands/backup_study.py',
 'backend/logging_app/views.py', 'backend/tutor/views.py',
 'frontend/src/pages/ExpertPortal.jsx', 'frontend/src/services/score.js',
 'frontend/src/services/api.js', 'frontend/src/services/tutorModel.js',
 'frontend/src/components/TutorPanel/AnswerOnlyPanel.jsx',
 'frontend/src/components/TutorPanel/ReasoningTracePanel.jsx',
 'frontend/src/pages/Workspace.jsx', 'frontend/src/components/ui/index.jsx',
 'frontend/src/pages/Dashboard.jsx']
release = {}
for rel in runtime:
    data = (candidate / rel).read_bytes()
    assert hashlib.sha256(data).hexdigest() == manifest[rel]
    release[rel] = {'expected_sha256': audit['files'].get(rel), 'sha256': manifest[rel],
                    'base64': base64.b64encode(data).decode()}
dependencies = {}
for rel in manifest:
    parts = Path(rel).parts
    if rel in runtime or rel == 'backend/trace_backend/settings.py':
        continue
    if rel.startswith('backend/') and ('tests' in parts or Path(rel).name.startswith(('test', 'qa_'))):
        continue
    if rel.startswith('frontend/tests/') or rel in ['frontend/vitest.config.js', 'frontend/eslint.config.js']:
        continue
    data = (candidate / rel).read_bytes()
    if Path(rel).suffix in {'.py', '.js', '.jsx', '.json', '.txt', '.css', '.mjs', '.html'}:
        data = data.replace(b'\r\n', b'\n')
    dependencies[rel] = hashlib.sha256(data).hexdigest()
(here / 'release.json').write_text(json.dumps(release, indent=2), encoding='utf-8')
(here / 'dependencies.json').write_text(json.dumps(dependencies, indent=2), encoding='utf-8')
with tarfile.open(here / 'candidate.tar.gz', 'w:gz') as archive:
    for rel in manifest:
        assert hashlib.sha256((candidate / rel).read_bytes()).hexdigest() == manifest[rel]
        archive.add(candidate / rel, arcname=rel, recursive=False)
print('ONE runtime release:', len(release), 'files;', len(dependencies), 'unchanged runtime dependencies guarded')
print('Header search, runner, bank and other existing functionality remain guarded dependencies.')
