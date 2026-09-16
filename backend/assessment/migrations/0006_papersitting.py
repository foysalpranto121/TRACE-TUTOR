import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0005_examsubmission_arm'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PaperSitting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('exam_type', models.CharField(max_length=20)),
                ('arm', models.CharField(blank=True, default='', max_length=20)),
                ('first_opened_at', models.DateTimeField(auto_now_add=True)),
                ('last_opened_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sittings', to=settings.AUTH_USER_MODEL)),
                ('submission', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sittings', to='assessment.examsubmission')),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('student', 'exam_type'), name='uniq_sitting_per_student_paper')],
            },
        ),
    ]
