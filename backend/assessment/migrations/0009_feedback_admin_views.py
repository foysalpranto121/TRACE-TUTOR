from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('assessment', '0008_assessmenttimeline')]

    operations = [
        migrations.CreateModel(
            name='ExpertFeedback', fields=[],
            options={'proxy': True, 'verbose_name': 'Expert feedback',
                     'verbose_name_plural': 'Expert feedback', 'indexes': [], 'constraints': []},
            bases=('assessment.expertgrade',),
        ),
        migrations.CreateModel(
            name='TeacherComment', fields=[],
            options={'proxy': True, 'verbose_name': 'Teacher comment',
                     'verbose_name_plural': 'Teacher comment', 'indexes': [], 'constraints': []},
            bases=('assessment.expertrating',),
        ),
    ]
