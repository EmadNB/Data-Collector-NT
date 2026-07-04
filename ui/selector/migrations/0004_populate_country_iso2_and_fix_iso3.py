from django.db import migrations


NAME_TO_ISO3 = {
    "Albania": "ALB",
    "Austria": "AUT",
    "Bosnia and Herzegovina": "BIH",
    "Belgium": "BEL",
    "Bulgaria": "BGR",
    "Switzerland": "CHE",
    "Cyprus": "CYP",
    "Czech Republic": "CZE",
    "Germany": "DEU",
    "Denmark": "DNK",
    "Algeria": "DZA",
    "Estonia": "EST",
    "Egypt": "EGY",
    "Spain": "ESP",
    "Finland": "FIN",
    "France": "FRA",
    "Greece": "GRC",
    "Croatia": "HRV",
    "Hungary": "HUN",
    "Ireland": "IRL",
    "Israel": "ISR",
    "Iceland": "ISL",
    "Italy": "ITA",
    "Lithuania": "LTU",
    "Luxembourg": "LUX",
    "Latvia": "LVA",
    "Libya": "LBY",
    "Morocco": "MAR",
    "Moldova": "MDA",
    "Montenegro": "MNE",
    "Macedonia": "MKD",
    "Malta": "MLT",
    "Netherlands": "NLD",
    "Norway": "NOR",
    "Poland": "POL",
    "Palestine": "PSE",
    "Portugal": "PRT",
    "Romania": "ROU",
    "Republic of Serbia": "SRB",
    "Sweden": "SWE",
    "Slovenia": "SVN",
    "Slovakia": "SVK",
    "Tunisia": "TUN",
    "Turkey": "TUR",
    "Ukraine": "UKR",
    "United Kingdom": "GBR",
    "Belarus": "BLR",
}


def forwards(apps, schema_editor):
    Country = apps.get_model("selector", "Country")
    Zone = apps.get_model("selector", "Zone")

    # 1) If someone changed iso3 to 2-letter codes, fix back to ISO3 (GeoJSON uses ISO3).
    for c in Country.objects.all():
        if isinstance(c.iso3, str) and len(c.iso3) == 2:
            iso3 = NAME_TO_ISO3.get(c.name)
            if iso3:
                c.iso3 = iso3
                c.save(update_fields=["iso3"])

    # 2) Populate iso2 using zone code prefixes (matches your zone naming: FR00 -> FR, UK00 -> UK, etc.)
    for c in Country.objects.all():
        if c.iso2:
            continue
        prefix = (
            Zone.objects.filter(country=c)
            .order_by("code")
            .values_list("code", flat=True)
            .first()
        )
        if prefix and isinstance(prefix, str) and len(prefix) >= 2:
            c.iso2 = prefix[:2]
            c.save(update_fields=["iso2"])


def backwards(apps, schema_editor):
    Country = apps.get_model("selector", "Country")
    Country.objects.update(iso2=None)


class Migration(migrations.Migration):
    dependencies = [
        ("selector", "0003_add_country_iso2"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=backwards),
    ]

