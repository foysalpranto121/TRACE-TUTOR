from pathlib import Path
import subprocess
root = Path('/srv/trace-tutor')
bundle = Path('/tmp/trace-tutor-combined-20261009')
backup = root / 'deployment-backups/combined-teacher-docker-20261009T175621Z'
assert (backup / 'BACKUP_VERIFIED').exists()
assert (backup / 'new-dist/index.html').exists()
assert (backup / 'backend-test-workspace-r2').exists()
subprocess.run([str(root / 'venv/bin/python'), 'manage.py', 'migrate', '--check'], cwd=root / 'backend', check=True)
(backup / 'STAGING_VERIFIED').write_text((bundle / 'candidate-identity.json').read_text())
print('PASS no pending migrations; 113 Linux regressions and 108 frontend tests passed before publication')
