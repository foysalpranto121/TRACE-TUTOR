from django.db import migrations, models


def backfill_arm(apps, schema_editor):
    """Existing submissions predate the field; the best available value is the arm the
    participant was enrolled in (nobody could switch before enrolment records existed)."""
    ExamSubmission = apps.get_model('assessment', 'ExamSubmission')
    ParticipantProfile = apps.get_model('accounts', 'ParticipantProfile')
    arms = {p.user_id: (p.enrolled_arm or p.assigned_arm) for p in ParticipantProfile.objects.all()}
    for submission in ExamSubmission.objects.filter(arm=''):
        submission.arm = arms.get(submission.student_id, '')
        submission.save(update_fields=['arm'])


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0004_submission_background_grading'),
        ('accounts', '0005_participantprofile_enrolled_arm'),
    ]

    operations = [
        migrations.AddField(
            model_name='examsubmission',
            name='arm',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.RunPython(backfill_arm, migrations.RunPython.noop),
    ]
