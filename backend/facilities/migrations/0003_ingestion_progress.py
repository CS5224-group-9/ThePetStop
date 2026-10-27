from django.db import migrations, models


def normalise_empty_licences(apps, schema_editor):
    apps.get_model("facilities", "Facility").objects.filter(
        licence_no__isnull=True
    ).update(licence_no="")


class Migration(migrations.Migration):
    dependencies = [("facilities", "0002_facility_syncrun_superseded")]
    operations = [
        migrations.RunPython(normalise_empty_licences, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="facility",
            name="licence_no",
            field=models.CharField(max_length=32, blank=True, default=""),
        ),
        migrations.RemoveConstraint(
            model_name="facilitysyncrun", name="fac_sync_one_running_source"
        ),
        migrations.AlterField(
            model_name="facilitysyncrun",
            name="status",
            field=models.CharField(
                max_length=16,
                default="running",
                choices=[
                    ("running", "Running"),
                    ("succeeded", "Succeeded"),
                    ("failed", "Failed"),
                    ("superseded", "Superseded"),
                    ("review_required", "Review required"),
                ],
            ),
        ),
        migrations.AddField(
            model_name="facilitysyncrun",
            name="stage",
            field=models.CharField(default="fetching", max_length=24),
        ),
        migrations.AddField(
            model_name="facilitysyncrun",
            name="last_activity_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="facilitysyncrun",
            name="expected_batch_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="facilitysyncrun",
            name="completed_batch_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="facilitysyncrun",
            name="retry_count",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
