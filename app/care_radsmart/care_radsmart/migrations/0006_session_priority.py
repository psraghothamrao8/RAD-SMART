import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('care_radsmart', '0005_time_bands_and_live_queue'),
    ]

    operations = [
        migrations.AddField(
            model_name='session',
            name='priority',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='session',
            name='priority_note',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='session',
            name='priority_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='session',
            name='priority_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
