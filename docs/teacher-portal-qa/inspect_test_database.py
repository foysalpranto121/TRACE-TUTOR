"""Read-only local PostgreSQL test-environment discovery. Never reads research tables."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'trace_backend.settings')
import django
django.setup()
from django.conf import settings
import psycopg2
d = settings.DATABASES['default']
assert d['HOST'] in ('localhost', '127.0.0.1', '::1'), 'Refusing remote inspection'
with psycopg2.connect(dbname='postgres', user=d['USER'], password=d['PASSWORD'],
                      host=d['HOST'], port=d['PORT'], connect_timeout=5) as connection:
    connection.set_session(readonly=True)
    with connection.cursor() as cursor:
        cursor.execute('SELECT rolcreatedb, rolsuper FROM pg_roles WHERE rolname = current_user')
        print('Configured local role privileges (CREATEDB, SUPERUSER):', cursor.fetchone())
        cursor.execute("SELECT datname FROM pg_database WHERE datname LIKE 'test_%' OR datname LIKE 'trace%qa%'")
        print('Existing disposable database names:', [row[0] for row in cursor.fetchall()])
