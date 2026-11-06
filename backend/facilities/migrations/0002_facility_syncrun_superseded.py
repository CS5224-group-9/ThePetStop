from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("facilities", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="facilitysyncrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("running", "Running"),
                    ("succeeded", "Succeeded"),
                    ("failed", "Failed"),
                    ("superseded", "Superseded"),
                ],
                default="running",
                max_length=12,
            ),
        )
    ]
