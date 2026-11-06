from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('assessment', '0009_feedback_admin_views'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(name='TeacherReviewAssignment', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('assigned_at', models.DateTimeField(auto_now_add=True)),
            ('expert_user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name='ItemReviewAssignment', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('item_key', models.CharField(max_length=50, unique=True)),
            ('assigned_at', models.DateTimeField(auto_now_add=True)),
            ('expert_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name='SubmissionReviewAssignment', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('assigned_at', models.DateTimeField(auto_now_add=True)),
            ('expert_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ('submission', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='assessment.examsubmission')),
        ]),
    ]
