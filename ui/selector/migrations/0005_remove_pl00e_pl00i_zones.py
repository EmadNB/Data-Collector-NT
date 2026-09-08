from django.db import migrations


REMOVED_CODES = ["PL00E", "PL00I"]


def forwards(apps, schema_editor):
    Zone = apps.get_model("selector", "Zone")
    Zone.objects.filter(code__in=REMOVED_CODES).delete()


def backwards(apps, schema_editor):
    Country = apps.get_model("selector", "Country")
    Zone = apps.get_model("selector", "Zone")
    poland, _ = Country.objects.get_or_create(name="Poland", defaults={"iso3": "POL", "iso2": "PL"})
    for code in REMOVED_CODES:
        Zone.objects.get_or_create(code=code, defaults={"country": poland})


class Migration(migrations.Migration):
    dependencies = [
        ("selector", "0004_populate_country_iso2_and_fix_iso3"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=backwards),
    ]
