from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('assessment', '0007_examsubmission_claimed_at'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(
        name='AssessmentTimeline',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('window_start', models.DateTimeField(blank=True, null=True)),
            ('window_end', models.DateTimeField(blank=True, null=True)),
            ('pre_started_at', models.DateTimeField(blank=True, null=True)),
            ('post_started_at', models.DateTimeField(blank=True, null=True)),
            ('transfer_started_at', models.DateTimeField(blank=True, null=True)),
            ('withdrawal_started_at', models.DateTimeField(blank=True, null=True)),
            ('is_synthetic', models.BooleanField(default=False)),
            ('provenance', models.JSONField(blank=True, default=dict)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('student', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='assessment_timeline', to=settings.AUTH_USER_MODEL)),
        ],
    )]
