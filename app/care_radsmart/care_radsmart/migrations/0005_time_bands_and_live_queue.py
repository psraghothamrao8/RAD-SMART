from django.db import migrations, models


def to_bands(apps, schema_editor):
    """A preferred exact time becomes the part of the day it falls in."""
    Course = apps.get_model("care_radsmart", "Course")
    for c in Course.objects.exclude(preferred_time=None):
        t = c.preferred_time
        c.time_band = ("morning" if t < 12 * 60 else "afternoon" if t < 17 * 60
                       else "evening" if t < 21 * 60 else "")
        c.save(update_fields=["time_band"])


class Migration(migrations.Migration):

    dependencies = [
        ('care_radsmart', '0004_demo_clock'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='time_band',
            field=models.CharField(blank=True, choices=[('', 'Any time'), ('morning', 'Morning (08:30-12:00)'), ('afternoon', 'Afternoon (12:00-17:00)'), ('evening', 'Evening (17:00-21:00)')], default='', max_length=16),
        ),
        migrations.RunPython(to_bands, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='course',
            name='preferred_time',
        ),
        migrations.AddField(
            model_name='session',
            name='out_of_turn',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='session',
            name='turn_note',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='slotrequest',
            name='band',
            field=models.CharField(blank=True, default='', max_length=16),
        ),
        migrations.AddField(
            model_name='slotrequest',
            name='source',
            field=models.CharField(choices=[('patient', 'Patient'), ('staff', 'Staff'), ('radsmart', 'RAD-SMART')], default='patient', max_length=16),
        ),
        migrations.AlterField(
            model_name='slotrequest',
            name='wanted',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='slotrequest',
            name='status',
            field=models.CharField(choices=[('proposed', 'Proposed'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('withdrawn', 'Withdrawn')], default='proposed', max_length=16),
        ),
        migrations.AddField(
            model_name='patientreply',
            name='band',
            field=models.CharField(blank=True, default='', max_length=16),
        ),
    ]
