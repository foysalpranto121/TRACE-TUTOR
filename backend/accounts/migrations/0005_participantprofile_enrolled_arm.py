from django.db import migrations, models

ARM_CHOICES = [('REASONING_VISIBLE', 'Treatment: Reasoning-Visible'), ('ANSWER_ONLY', 'Control: Answer-Only')]


def backfill_enrolled_arm(apps, schema_editor):
    """The arm a participant was allocated at enrolment. For existing rows, the current
    arm is the original unless an ARM_SWITCH event says otherwise - in which case the
    earliest switch's `from` is what they were enrolled in."""
    ParticipantProfile = apps.get_model('accounts', 'ParticipantProfile')
    InteractionLog = apps.get_model('logging_app', 'InteractionLog')
    for profile in ParticipantProfile.objects.all():
        original = profile.assigned_arm
        first_switch = (InteractionLog.objects
                        .filter(user_id=profile.user_id, event_type='ARM_SWITCH')
                        .order_by('timestamp').first())
        payload = first_switch.payload if first_switch and isinstance(first_switch.payload, dict) else {}
        if payload.get('from') in dict(ARM_CHOICES):
            original = payload['from']
        profile.enrolled_arm = original
        profile.save(update_fields=['enrolled_arm'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_participant_withdrawal'),
        ('logging_app', '0002_alter_interactionlog_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='participantprofile',
            name='enrolled_arm',
            field=models.CharField(blank=True, choices=ARM_CHOICES, default='', max_length=20),
        ),
        migrations.RunPython(backfill_enrolled_arm, migrations.RunPython.noop),
    ]
