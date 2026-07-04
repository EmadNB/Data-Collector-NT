from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("selector", "0002_seed_countries_zones"),
    ]

    operations = [
        migrations.AddField(
            model_name="country",
            name="iso2",
            field=models.CharField(blank=True, max_length=2, null=True, unique=True),
        ),
    ]

