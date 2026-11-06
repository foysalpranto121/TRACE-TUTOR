"""Disposable PostgreSQL namespace; never includes public in search_path."""
import re
from django.conf import settings
from django.core.management import call_command
from django.db import connections
from psycopg2 import sql
from trace_backend.qa_runner import TeacherQARunner


class ProtocolSchemaRunner(TeacherQARunner):
    def setup_databases(self, **kwargs):
        schema = settings.PROTOCOL_QA_SCHEMA
        assert re.fullmatch(r'trace_protocol_qa_[a-f0-9]{12}', schema)
        connection = connections['default']
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            cursor.execute('SELECT current_schema()')
            assert cursor.fetchone()[0] == schema
        call_command('makemigrations', check=True, dry_run=True, verbosity=0)
        call_command('migrate', verbosity=0, interactive=False)
        return schema

    def teardown_databases(self, old_config, **kwargs):
        assert old_config == settings.PROTOCOL_QA_SCHEMA
        with connections['default'].cursor() as cursor:
            cursor.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(old_config)))
        connections.close_all()
