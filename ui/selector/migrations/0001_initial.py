from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Country",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("iso3", models.CharField(max_length=3, unique=True)),
                ("name", models.CharField(max_length=128)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Zone",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=8, unique=True)),
                (
                    "country",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="zones", to="selector.country"),
                ),
            ],
            options={
                "ordering": ["code"],
            },
        ),
    ]

