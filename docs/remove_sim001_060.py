"""Back up, then remove exactly the 60 user-requested session imports.

Run via manage.py shell with REMOVAL_STAGE=backup or delete. Deletion requires a
verified backup directory and refuses any changed data or unrecognised accounts.
"""
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from django.apps import apps
from django.contrib.auth.models import User
from django.core import serializers
from django.db import transaction
from django.db.models.deletion import Collector
from django.utils import timezone
from accounts.models import ParticipantProfile
from assessment.models import ExamSubmission, ExpertGrade
from logging_app.models import InteractionLog

CODES = [f'SIM-{number:03}' for number in range(1, 61)]
BACKUP_ROOT = Path('/srv/trace-tutor/deployment-backups').resolve()


def checked_accounts():
    profiles = list(ParticipantProfile.objects.filter(participant_code__in=CODES).select_related('user').order_by('participant_code'))
    assert len(profiles) == 60 and {p.participant_code for p in profiles} == set(CODES), 'Expected all 60 imported profiles'
    for profile in profiles:
        user = profile.user
        assert profile.role == 'STUDENT' and not user.is_staff and not user.is_superuser
        assert user.username == profile.participant_code
        receipt = InteractionLog.objects.get(
            user=user, event_type='SUMMARY_IMPORT',
            payload__import_key=f'user-supplied-participant-summary:{profile.participant_code}:v1',
        )
        assert receipt.payload['source']['participant_id'] == profile.participant_code
    return profiles, sorted(p.user_id for p in profiles)


def collect_snapshot(user_ids):
    collector = Collector(using='default')
    collector.collect(User.objects.filter(pk__in=user_ids))
    objects = {}
    for model, rows in collector.data.items():
        for row in rows:
            objects[(model._meta.label_lower, str(row.pk))] = row
    for queryset in collector.fast_deletes:
        for row in queryset:
            objects[(row._meta.label_lower, str(row.pk))] = row
    # No SET_NULL change to a surviving record is expected for these imports.
    for batches in collector.field_updates.values():
        for batch in batches:
            assert not (batch.exists() if hasattr(batch, 'exists') else bool(batch)), 'Unexpected surviving-row update; inspect before removal'
    ordered = [objects[key] for key in sorted(objects)]
    fixture = serializers.serialize('json', ordered)
    counts, pks = {}, {}
    for row in ordered:
        label = row._meta.label_lower
        counts[label] = counts.get(label, 0) + 1
        pks.setdefault(label, []).append(row.pk)
    assert counts['auth.user'] == counts['accounts.participantprofile'] == 60
    assert counts['assessment.examsubmission'] == 237
    assert counts['logging_app.interactionlog'] == 120
    return collector, fixture, counts, pks


def write_private(path, content):
    with path.open('x', encoding='utf-8') as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def unaffected_fingerprints(user_ids, submission_ids):
    querysets = {
        'users': User.objects.exclude(pk__in=user_ids),
        'profiles': ParticipantProfile.objects.exclude(user_id__in=user_ids),
        'submissions': ExamSubmission.objects.exclude(student_id__in=user_ids),
        'logs': InteractionLog.objects.exclude(user_id__in=user_ids),
        'teacher_grades': ExpertGrade.objects.exclude(submission_id__in=submission_ids).exclude(expert_user_id__in=user_ids),
    }
    return {name: hashlib.sha256(serializers.serialize('json', qs.order_by('pk')).encode()).hexdigest()
            for name, qs in querysets.items()}


def backup():
    _, user_ids = checked_accounts()
    _, fixture, counts, pks = collect_snapshot(user_ids)
    directory = BACKUP_ROOT / f'remove-sim001-060-20261025-{uuid4().hex[:12]}'
    assert directory.resolve().parent == BACKUP_ROOT
    directory.mkdir(mode=0o700)
    fixture_path = directory / 'affected-rows.json'
    write_private(fixture_path, fixture)
    digest = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    assert digest == hashlib.sha256(fixture.encode()).hexdigest()
    manifest = {
        'created_at': timezone.now().isoformat(), 'purpose': 'User requested removal of all 60 session-imported students',
        'participant_codes': CODES, 'user_ids': user_ids, 'row_counts': counts, 'pks_by_model': pks,
        'fixture_sha256': digest,
    }
    write_private(directory / 'manifest.json', json.dumps(manifest, indent=2))
    print('REMOVAL_BACKUP_VERIFIED', json.dumps({'directory': str(directory), 'sha256': digest, 'row_counts': counts}), flush=True)


def delete():
    directory = Path(os.environ['REMOVAL_BACKUP_DIRECTORY']).resolve()
    assert directory.parent == BACKUP_ROOT and directory.name.startswith('remove-sim001-060-20261025-')
    manifest = json.loads((directory / 'manifest.json').read_text())
    assert manifest['participant_codes'] == CODES
    assert hashlib.sha256((directory / 'affected-rows.json').read_bytes()).hexdigest() == manifest['fixture_sha256']
    assert not (directory / 'REMOVED.json').exists(), 'Removal already completed'
    with transaction.atomic():
        user_ids = manifest['user_ids']
        assert sorted(User.objects.filter(pk__in=user_ids).select_for_update().values_list('pk', flat=True)) == user_ids
        # Lock every backed-up row before checking the snapshot again.
        for label, pks in manifest['pks_by_model'].items():
            model = apps.get_model(label)
            assert len(list(model._base_manager.filter(pk__in=pks).select_for_update().values_list('pk', flat=True))) == len(pks)
        _, current_ids = checked_accounts()
        assert current_ids == user_ids
        collector, fixture, counts, pks = collect_snapshot(user_ids)
        assert hashlib.sha256(fixture.encode()).hexdigest() == manifest['fixture_sha256'], 'Data changed after backup; refresh backup before removal'
        assert counts == manifest['row_counts'] and pks == manifest['pks_by_model']
        submission_ids = pks['assessment.examsubmission']
        unaffected_before = unaffected_fingerprints(user_ids, submission_ids)
        total, deleted_by_model = collector.delete()
        assert not User.objects.filter(pk__in=user_ids).exists()
        assert not User.objects.filter(username__in=CODES).exists()
        assert not ParticipantProfile.objects.filter(participant_code__in=CODES).exists()
        assert not ExamSubmission.objects.filter(student_id__in=user_ids).exists()
        assert not InteractionLog.objects.filter(user_id__in=user_ids).exists()
        assert not ExpertGrade.objects.filter(submission_id__in=submission_ids).exists()
        assert unaffected_fingerprints(user_ids, submission_ids) == unaffected_before, 'Unrelated data changed; rolling back'
        assert total == sum(counts.values())
    result = {'deleted_rows': total, 'deleted_by_model': deleted_by_model,
              'remaining_imported_profiles': 0, 'unrelated_data_verified_unchanged': True,
              'backup_directory': str(directory), 'completed_at': timezone.now().isoformat()}
    write_private(directory / 'REMOVED.json', json.dumps(result, indent=2))
    print('REMOVAL_COMPLETED', json.dumps(result), flush=True)


os.umask(0o077)
{'backup': backup, 'delete': delete}[os.environ['REMOVAL_STAGE']]()
